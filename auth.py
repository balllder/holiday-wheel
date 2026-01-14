"""Authentication blueprint for Holiday Wheel."""

import os
import re
import secrets
import time
from functools import wraps

import requests
from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from db_auth import (
    db_clear_remember_token,
    db_create_user,
    db_delete_room,
    db_delete_user,
    db_get_user_by_email,
    db_get_user_by_id,
    db_get_user_by_remember_token,
    db_get_user_by_verification_token,
    db_get_user_stats,
    db_list_active_rooms,
    db_list_all_users,
    db_manually_verify_user,
    db_set_remember_token,
    db_set_verification_token,
    db_update_last_login,
    db_user_exists,
    db_verify_user,
)
from email_service import send_verification_email

# reCAPTCHA configuration
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "")

# Host code for admin access
HOST_CODE = os.environ.get("HOST_CODE", "holiday")

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def login_required(f):
    """Decorator to require authentication."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = get_current_user()
        if not user:
            if request.is_json or request.headers.get("Accept") == "application/json":
                return jsonify({"ok": False, "error": "Authentication required"}), 401
            return redirect(url_for("auth.login"))
        return f(*args, **kwargs)

    return decorated_function


def get_current_user():
    """Get current user from session or remember token."""
    if "user_id" in session:
        user = db_get_user_by_id(session["user_id"])
        if user:
            return user

    remember_token = request.cookies.get("remember_token")
    if remember_token:
        user = db_get_user_by_remember_token(remember_token)
        if user:
            session["user_id"] = user["id"]
            session["display_name"] = user["display_name"]
            return user

    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Login page and handler."""
    if request.method == "GET":
        if get_current_user():
            return redirect(url_for("auth.lobby"))
        return render_template("auth/login.html")

    data = request.get_json() if request.is_json else request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    remember_me = data.get("remember_me", False)

    if not email or not password:
        return jsonify({"ok": False, "error": "Email and password are required"}), 400

    user = db_get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"ok": False, "error": "Invalid email or password"}), 401

    if not user["verified"]:
        return jsonify({"ok": False, "error": "Please verify your email before logging in"}), 403

    session["user_id"] = user["id"]
    session["display_name"] = user["display_name"]
    session.permanent = bool(remember_me)

    db_update_last_login(user["id"])

    response = jsonify({"ok": True, "user": {"id": user["id"], "display_name": user["display_name"]}})

    if remember_me:
        remember_token = secrets.token_urlsafe(32)
        db_set_remember_token(user["id"], remember_token)
        response.set_cookie("remember_token", remember_token, max_age=30 * 24 * 60 * 60, httponly=True, samesite="Lax")

    return response


@auth_bp.route("/api/login", methods=["POST"])
def api_login():
    """API login endpoint for mobile apps. Returns a token for authentication."""
    data = request.get_json() if request.is_json else {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not email or not password:
        return jsonify({"ok": False, "error": "Email and password are required"}), 400

    user = db_get_user_by_email(email)

    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"ok": False, "error": "Invalid email or password"}), 401

    if not user["verified"]:
        return jsonify({"ok": False, "error": "Please verify your email before logging in"}), 403

    # Generate a token for the mobile app
    token = secrets.token_urlsafe(32)
    db_set_remember_token(user["id"], token)
    db_update_last_login(user["id"])

    return jsonify({
        "ok": True,
        "token": token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        },
    })


@auth_bp.route("/api/verify", methods=["GET"])
def api_verify_token():
    """Verify an API token is still valid."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "No token provided"}), 401

    token = auth_header[7:]  # Remove "Bearer " prefix
    user = db_get_user_by_remember_token(token)

    if not user:
        return jsonify({"ok": False, "error": "Invalid token"}), 401

    return jsonify({
        "ok": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"],
        },
    })


@auth_bp.route("/api/rooms", methods=["GET"])
def api_rooms():
    """Get list of active rooms (requires token auth)."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return jsonify({"ok": False, "error": "No token provided"}), 401

    token = auth_header[7:]
    user = db_get_user_by_remember_token(token)

    if not user:
        return jsonify({"ok": False, "error": "Invalid token"}), 401

    rooms = db_list_active_rooms()
    return jsonify({"ok": True, "rooms": rooms})


# Minimum score for reCAPTCHA v3 (0.0 = bot, 1.0 = human)
RECAPTCHA_MIN_SCORE = float(os.environ.get("RECAPTCHA_MIN_SCORE", "0.5"))


def verify_recaptcha(token: str, expected_action: str = "register") -> tuple[bool, str]:
    """Verify reCAPTCHA v3 token with Google.

    Returns (success, error_message) tuple.
    """
    if not RECAPTCHA_SECRET_KEY:
        return True, ""  # Skip verification if not configured

    if not token:
        return False, "No CAPTCHA token provided"

    try:
        response = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={"secret": RECAPTCHA_SECRET_KEY, "response": token},
            timeout=10,
        )
        result = response.json()

        if not result.get("success", False):
            error_codes = result.get("error-codes", [])
            return False, f"CAPTCHA verification failed: {', '.join(error_codes)}"

        # Check action matches (prevents token reuse across different forms)
        actual_action = result.get("action", "")
        if actual_action != expected_action:
            return False, f"CAPTCHA action mismatch (expected: {expected_action}, got: {actual_action})"

        # Check score meets threshold
        score = result.get("score", 0.0)
        if score < RECAPTCHA_MIN_SCORE:
            return False, f"CAPTCHA score too low ({score:.2f} < {RECAPTCHA_MIN_SCORE})"

        return True, ""
    except Exception as e:
        return False, f"CAPTCHA verification error: {str(e)}"


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Registration page and handler."""
    if request.method == "GET":
        if get_current_user():
            return redirect(url_for("auth.lobby"))
        return render_template("auth/register.html", recaptcha_site_key=RECAPTCHA_SITE_KEY)

    data = request.get_json() if request.is_json else request.form
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    display_name = (data.get("display_name") or "").strip()
    captcha_token = data.get("captcha_token") or ""

    errors = []

    # Verify reCAPTCHA if configured
    if RECAPTCHA_SECRET_KEY:
        captcha_ok, captcha_error = verify_recaptcha(captcha_token)
        if not captcha_ok:
            errors.append(captcha_error or "CAPTCHA verification failed")

    if not email or not EMAIL_REGEX.match(email):
        errors.append("Valid email is required")

    if len(password) < 8:
        errors.append("Password must be at least 8 characters")

    if not display_name or len(display_name) < 2:
        errors.append("Display name must be at least 2 characters")

    if len(display_name) > 24:
        errors.append("Display name must be 24 characters or less")

    if errors:
        return jsonify({"ok": False, "errors": errors}), 400

    if db_user_exists(email):
        return jsonify({"ok": False, "errors": ["Email already registered"]}), 409

    password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
    verification_token = secrets.token_urlsafe(32)
    token_expires = int(time.time()) + 86400  # 24 hours

    try:
        db_create_user(email, password_hash, display_name, verification_token, token_expires)
    except Exception as e:
        return jsonify({"ok": False, "errors": [f"Failed to create account: {str(e)}"]}), 500

    try:
        send_verification_email(email, verification_token)
    except Exception as e:
        # User was created but email failed - still return success with warning
        return jsonify({"ok": True, "message": f"Account created but email failed to send: {str(e)}. Contact support."})

    return jsonify({"ok": True, "message": "Registration successful! Please check your email to verify your account."})


@auth_bp.route("/verify/<token>")
def verify_email(token):
    """Email verification handler."""
    user = db_get_user_by_verification_token(token)

    if not user:
        return render_template(
            "auth/verify_result.html", success=False, message="Invalid or expired verification link."
        )

    if user["verification_token_expires"] < int(time.time()):
        return render_template(
            "auth/verify_result.html", success=False, message="Verification link has expired. Please register again."
        )

    db_verify_user(user["id"])

    return render_template(
        "auth/verify_result.html", success=True, message="Email verified successfully! You can now log in."
    )


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Logout handler."""
    user_id = session.get("user_id")
    if user_id:
        db_clear_remember_token(user_id)

    session.clear()
    response = jsonify({"ok": True})
    response.delete_cookie("remember_token")
    return response


@auth_bp.route("/lobby")
@login_required
def lobby():
    """Room selection lobby page."""
    user = get_current_user()
    return render_template("lobby.html", user=user)


@auth_bp.route("/rooms")
@login_required
def list_rooms():
    """List active rooms API endpoint."""
    rooms = db_list_active_rooms(hours=24)

    # Import GAMES to get player counts
    try:
        from app import GAMES

        for room in rooms:
            game = GAMES.get(room["name"])
            if game:
                room["player_count"] = sum(1 for p in game.players if p.claimed_sid)
                room["total_slots"] = len(game.players)
            else:
                room["player_count"] = 0
                room["total_slots"] = 8
    except ImportError:
        for room in rooms:
            room["player_count"] = 0
            room["total_slots"] = 8

    return jsonify({"ok": True, "rooms": rooms})


@auth_bp.route("/me")
def me():
    """Get current user info."""
    user = get_current_user()
    if not user:
        return jsonify({"ok": False, "user": None})
    return jsonify(
        {"ok": True, "user": {"id": user["id"], "email": user["email"], "display_name": user["display_name"]}}
    )


# ---- Admin Routes ----


def require_host(f):
    """Decorator to require host authentication via session."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("is_host"):
            return jsonify({"ok": False, "error": "Host authentication required"}), 403
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route("/admin")
@login_required
def admin():
    """Admin page."""
    user = get_current_user()
    return render_template("admin.html", user=user)


@auth_bp.route("/admin/verify-host", methods=["POST"])
@login_required
def verify_host():
    """Verify host code and grant admin access."""
    data = request.get_json() if request.is_json else request.form
    code = data.get("code", "")

    if code != HOST_CODE:
        return jsonify({"ok": False, "error": "Invalid host code"}), 401

    session["is_host"] = True
    return jsonify({"ok": True, "message": "Host access granted"})


@auth_bp.route("/admin/logout-host", methods=["POST"])
@login_required
def logout_host():
    """Revoke host access."""
    session.pop("is_host", None)
    return jsonify({"ok": True})


@auth_bp.route("/admin/users")
@login_required
@require_host
def admin_list_users():
    """List all users for admin."""
    users = db_list_all_users()
    stats = db_get_user_stats()
    return jsonify({"ok": True, "users": users, "stats": stats})


@auth_bp.route("/admin/users/<int:user_id>", methods=["DELETE"])
@login_required
@require_host
def admin_delete_user(user_id):
    """Delete a user."""
    current_user = get_current_user()
    if current_user and current_user["id"] == user_id:
        return jsonify({"ok": False, "error": "Cannot delete yourself"}), 400

    if db_delete_user(user_id):
        return jsonify({"ok": True, "message": "User deleted"})
    return jsonify({"ok": False, "error": "User not found"}), 404


@auth_bp.route("/admin/users/<int:user_id>/verify", methods=["POST"])
@login_required
@require_host
def admin_verify_user(user_id):
    """Manually verify a user."""
    if db_manually_verify_user(user_id):
        return jsonify({"ok": True, "message": "User verified"})
    return jsonify({"ok": False, "error": "User not found or already verified"}), 404


@auth_bp.route("/admin/users/<int:user_id>/resend", methods=["POST"])
@login_required
@require_host
def admin_resend_verification(user_id):
    """Resend verification email to user."""
    user = db_get_user_by_id(user_id)
    if not user:
        return jsonify({"ok": False, "error": "User not found"}), 404

    if user["verified"]:
        return jsonify({"ok": False, "error": "User already verified"}), 400

    # Generate new token
    token = secrets.token_urlsafe(32)
    expires = int(time.time()) + 86400  # 24 hours
    db_set_verification_token(user_id, token, expires)

    try:
        send_verification_email(user["email"], token)
        return jsonify({"ok": True, "message": f"Verification email sent to {user['email']}"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"Failed to send email: {str(e)}"}), 500


@auth_bp.route("/admin/rooms")
@login_required
@require_host
def admin_list_rooms():
    """List all active rooms for admin."""
    rooms = db_list_active_rooms(hours=168)  # Last 7 days

    # Get player counts from GAMES
    try:
        from app import GAMES

        for room in rooms:
            game = GAMES.get(room["name"])
            if game:
                room["player_count"] = sum(1 for p in game.players if p.claimed_sid)
                room["total_slots"] = len(game.players)
            else:
                room["player_count"] = 0
                room["total_slots"] = 8
    except ImportError:
        for room in rooms:
            room["player_count"] = 0
            room["total_slots"] = 8

    return jsonify({"ok": True, "rooms": rooms})


@auth_bp.route("/admin/rooms/<room_name>", methods=["DELETE"])
@login_required
@require_host
def admin_delete_room(room_name):
    """Delete a room entirely."""
    from app import GAMES

    # Remove from in-memory games
    if room_name in GAMES:
        del GAMES[room_name]

    # Remove from database
    db_delete_room(room_name)

    return jsonify({"ok": True, "message": f"Room '{room_name}' deleted"})


@auth_bp.route("/admin/rooms/<room_name>/players")
@login_required
@require_host
def admin_get_room_players(room_name):
    """Get list of players in a room with user details."""
    from app import GAMES

    if room_name not in GAMES:
        return jsonify({"ok": True, "players": []})

    game = GAMES[room_name]
    players = []
    for i, p in enumerate(game.players):
        player_info = {
            "idx": i,
            "name": p.name,
            "user_id": p.claimed_user_id,
            "connected": p.claimed_sid is not None,
            "total": p.total,
        }
        if p.claimed_user_id:
            user = db_get_user_by_id(p.claimed_user_id)
            if user:
                player_info["email"] = user["email"]
        players.append(player_info)

    return jsonify({"ok": True, "players": players})


@auth_bp.route("/admin/rooms/<room_name>/players", methods=["POST"])
@login_required
@require_host
def admin_add_player(room_name):
    """Add a user as a player to a room."""
    from app import GAMES, Player, broadcast, get_game

    data = request.get_json() or {}
    user_id = data.get("user_id")

    if not user_id:
        return jsonify({"ok": False, "error": "user_id required"}), 400

    user = db_get_user_by_id(user_id)
    if not user:
        return jsonify({"ok": False, "error": "User not found"}), 404

    # Ensure game exists
    if room_name not in GAMES:
        get_game(room_name)

    game = GAMES[room_name]

    # Check if user already in game
    for p in game.players:
        if p.claimed_user_id == user_id:
            return jsonify({"ok": False, "error": "User already in game"}), 409

    # Add player (not connected yet)
    new_id = len(game.players)
    game.players.append(Player(id=new_id, name=user["display_name"], claimed_sid=None, claimed_user_id=user_id))
    broadcast(room_name)

    return jsonify({"ok": True, "player_idx": new_id})


@auth_bp.route("/admin/rooms/<room_name>/players/<int:player_idx>", methods=["DELETE"])
@login_required
@require_host
def admin_remove_player(room_name, player_idx):
    """Remove a player from a room."""
    from app import GAMES, broadcast

    if room_name not in GAMES:
        return jsonify({"ok": False, "error": "Room not found"}), 404

    game = GAMES[room_name]
    if player_idx < 0 or player_idx >= len(game.players):
        return jsonify({"ok": False, "error": "Invalid player index"}), 400

    # Remove player
    removed = game.players.pop(player_idx)

    # Renumber remaining players
    for i, p in enumerate(game.players):
        p.id = i

    # Adjust active_idx if needed
    if game.active_idx >= len(game.players):
        game.active_idx = 0 if game.players else 0

    broadcast(room_name)

    return jsonify({"ok": True, "message": f"Removed player '{removed.name}'"})


@auth_bp.route("/admin/users/available/<room_name>")
@login_required
@require_host
def admin_get_available_users(room_name):
    """Get verified users not currently in a room."""
    from app import GAMES

    all_users = db_list_all_users()

    # Get user IDs already in the room
    in_room = set()
    if room_name in GAMES:
        for p in GAMES[room_name].players:
            if p.claimed_user_id:
                in_room.add(p.claimed_user_id)

    available = [
        {"id": u["id"], "display_name": u["display_name"], "email": u["email"]}
        for u in all_users
        if u["id"] not in in_room and u["verified"]
    ]

    return jsonify({"ok": True, "users": available})


# ---- Pack Management Routes ----


@auth_bp.route("/admin/packs")
@login_required
@require_host
def admin_list_packs():
    """List all puzzle packs."""
    from app import db_list_packs

    packs = db_list_packs()
    return jsonify({"ok": True, "packs": packs})


@auth_bp.route("/admin/packs", methods=["POST"])
@login_required
@require_host
def admin_create_pack():
    """Create a new pack with puzzles from text format."""
    from app import db_add_puzzles, db_get_pack_id

    data = request.get_json() if request.is_json else request.form
    pack_name = (data.get("name") or "").strip()
    puzzles_text = (data.get("puzzles") or "").strip()

    if not pack_name:
        return jsonify({"ok": False, "error": "Pack name is required"}), 400

    if not puzzles_text:
        return jsonify({"ok": False, "error": "Puzzles are required"}), 400

    # Parse lines: "Category | Answer"
    lines = []
    for line in puzzles_text.split("\n"):
        line = line.strip()
        if not line or "|" not in line:
            continue
        parts = line.split("|", 1)
        if len(parts) == 2:
            cat = parts[0].strip()
            ans = parts[1].strip()
            if cat and ans:
                lines.append((cat, ans))

    if not lines:
        return jsonify({"ok": False, "error": "No valid puzzles found. Use format: Category | Answer"}), 400

    try:
        pack_id = db_get_pack_id(pack_name)
        added = db_add_puzzles(lines, pack_id)
        return jsonify(
            {"ok": True, "pack_id": pack_id, "added": added, "message": f"Added {added} puzzles to '{pack_name}'"}
        )
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@auth_bp.route("/admin/packs/import", methods=["POST"])
@login_required
@require_host
def admin_import_packs():
    """Import packs from JSON file."""
    import json

    from app import db_add_puzzles, db_get_pack_id

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"}), 400

    f = request.files["file"]
    try:
        payload = json.load(f.stream)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON file"}), 400

    packs = payload.get("packs")
    if not isinstance(packs, list) or not packs:
        return jsonify({"ok": False, "error": "JSON must contain 'packs' array"}), 400

    total_added = 0
    created_or_updated = []

    for pack in packs:
        name = str(pack.get("name", "")).strip()
        puzzles = pack.get("puzzles", [])
        if not name or not isinstance(puzzles, list) or not puzzles:
            continue

        pack_id = db_get_pack_id(name)

        lines = []
        for pz in puzzles:
            cat = str(pz.get("category", "")).strip()
            ans = str(pz.get("answer", "")).strip()
            if cat and ans:
                lines.append((cat, ans))

        if lines:
            total_added += db_add_puzzles(lines, pack_id)
            created_or_updated.append({"name": name, "added": len(lines)})

    return jsonify({"ok": True, "total_added": total_added, "packs": created_or_updated})


@auth_bp.route("/admin/packs/<int:pack_id>", methods=["DELETE"])
@login_required
@require_host
def admin_delete_pack(pack_id):
    """Delete a puzzle pack and its puzzles."""
    from app import db_connect

    with db_connect() as con:
        # Check if pack exists
        pack = con.execute("SELECT name FROM packs WHERE id=?", (pack_id,)).fetchone()
        if not pack:
            return jsonify({"ok": False, "error": "Pack not found"}), 404

        # Delete puzzles and pack
        con.execute("DELETE FROM puzzles WHERE pack_id=?", (pack_id,))
        con.execute("DELETE FROM packs WHERE id=?", (pack_id,))
        con.commit()

    return jsonify({"ok": True, "message": f"Deleted pack '{pack['name']}' and its puzzles"})


# ---- Room Config Routes ----


@auth_bp.route("/admin/config/<room>")
@login_required
@require_host
def admin_get_config(room):
    """Get room configuration."""
    from app import db_get_room_config

    config = db_get_room_config(room)
    return jsonify({"ok": True, "config": config})


@auth_bp.route("/admin/config/<room>", methods=["POST"])
@login_required
@require_host
def admin_set_config(room):
    """Set room configuration."""
    from app import db_set_active_pack, db_set_room_config

    data = request.get_json() if request.is_json else {}

    vowel_cost = data.get("vowel_cost")
    final_seconds = data.get("final_seconds")
    final_jackpot = data.get("final_jackpot")
    prize_cash_csv = data.get("prize_cash_csv")
    active_pack_id = data.get("active_pack_id")

    # Validate and convert
    try:
        if vowel_cost is not None:
            vowel_cost = int(vowel_cost)
        if final_seconds is not None:
            final_seconds = int(final_seconds)
        if final_jackpot is not None:
            final_jackpot = int(final_jackpot)

        prize_values = None
        if prize_cash_csv:
            prize_values = [int(v.strip()) for v in str(prize_cash_csv).split(",") if v.strip().isdigit()]
    except (ValueError, TypeError) as e:
        return jsonify({"ok": False, "error": f"Invalid value: {e}"}), 400

    # Update config - build config dict
    cfg = {}
    if vowel_cost is not None:
        cfg["vowel_cost"] = vowel_cost
    if final_seconds is not None:
        cfg["final_seconds"] = final_seconds
    if final_jackpot is not None:
        cfg["final_jackpot"] = final_jackpot
    if prize_values is not None:
        cfg["prize_replace_cash_values"] = prize_values
    if cfg:
        db_set_room_config(room, cfg)

    # Update active pack if provided
    if active_pack_id is not None:
        pack_id = int(active_pack_id) if active_pack_id else None
        db_set_active_pack(room, pack_id)

    return jsonify({"ok": True, "message": f"Configuration saved for room '{room}'"})
