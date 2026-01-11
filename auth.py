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
    db_get_user_by_email,
    db_get_user_by_id,
    db_get_user_by_remember_token,
    db_get_user_by_verification_token,
    db_list_active_rooms,
    db_set_remember_token,
    db_update_last_login,
    db_user_exists,
    db_verify_user,
)
from email_service import send_verification_email

# reCAPTCHA configuration
RECAPTCHA_SITE_KEY = os.environ.get("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.environ.get("RECAPTCHA_SECRET_KEY", "")

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

    response = jsonify({
        "ok": True,
        "user": {"id": user["id"], "display_name": user["display_name"]}
    })

    if remember_me:
        remember_token = secrets.token_urlsafe(32)
        db_set_remember_token(user["id"], remember_token)
        response.set_cookie(
            "remember_token",
            remember_token,
            max_age=30 * 24 * 60 * 60,
            httponly=True,
            samesite="Lax"
        )

    return response


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
            timeout=10
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
        return jsonify({
            "ok": True,
            "message": f"Account created but email failed to send: {str(e)}. Contact support."
        })

    return jsonify({
        "ok": True,
        "message": "Registration successful! Please check your email to verify your account."
    })


@auth_bp.route("/verify/<token>")
def verify_email(token):
    """Email verification handler."""
    user = db_get_user_by_verification_token(token)

    if not user:
        return render_template("auth/verify_result.html", success=False,
                               message="Invalid or expired verification link.")

    if user["verification_token_expires"] < int(time.time()):
        return render_template("auth/verify_result.html", success=False,
                               message="Verification link has expired. Please register again.")

    db_verify_user(user["id"])

    return render_template("auth/verify_result.html", success=True,
                           message="Email verified successfully! You can now log in.")


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
    return jsonify({
        "ok": True,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "display_name": user["display_name"]
        }
    })
