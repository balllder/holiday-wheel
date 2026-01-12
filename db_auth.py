"""Authentication database functions for Holiday Wheel."""

import os
import sqlite3
import time
from typing import Any, Dict, List, Optional

DB_PATH = os.environ.get("DB_PATH", "puzzles.db")


def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def db_init_auth():
    """Initialize authentication tables."""
    with db_connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL,
            verified INTEGER NOT NULL DEFAULT 0,
            verification_token TEXT,
            verification_token_expires INTEGER,
            reset_token TEXT,
            reset_token_expires INTEGER,
            created_at INTEGER NOT NULL,
            last_login_at INTEGER,
            remember_token TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
        CREATE INDEX IF NOT EXISTS idx_users_verification_token ON users(verification_token);
        CREATE INDEX IF NOT EXISTS idx_users_remember_token ON users(remember_token);

        CREATE TABLE IF NOT EXISTS rooms (
            name TEXT PRIMARY KEY,
            created_by INTEGER,
            created_at INTEGER NOT NULL,
            last_activity_at INTEGER NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(created_by) REFERENCES users(id)
        );

        CREATE INDEX IF NOT EXISTS idx_rooms_last_activity ON rooms(last_activity_at);
        """)
        con.commit()


def db_user_exists(email: str) -> bool:
    """Check if a user with this email already exists."""
    with db_connect() as con:
        row = con.execute("SELECT 1 FROM users WHERE email=?", (email.lower(),)).fetchone()
        return row is not None


def db_create_user(
    email: str,
    password_hash: str,
    display_name: str,
    verification_token: str,
    token_expires: int
) -> int:
    """Create a new user and return their ID."""
    now = int(time.time())
    with db_connect() as con:
        cursor = con.execute(
            """INSERT INTO users (email, password_hash, display_name, verification_token,
               verification_token_expires, created_at) VALUES (?,?,?,?,?,?)""",
            (email.lower(), password_hash, display_name, verification_token, token_expires, now)
        )
        con.commit()
        return cursor.lastrowid


def db_get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Get user by email address."""
    with db_connect() as con:
        row = con.execute("SELECT * FROM users WHERE email=?", (email.lower(),)).fetchone()
        return dict(row) if row else None


def db_get_user_by_id(user_id: int) -> Optional[Dict[str, Any]]:
    """Get user by ID."""
    with db_connect() as con:
        row = con.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()
        return dict(row) if row else None


def db_get_user_by_verification_token(token: str) -> Optional[Dict[str, Any]]:
    """Get user by verification token."""
    with db_connect() as con:
        row = con.execute("SELECT * FROM users WHERE verification_token=?", (token,)).fetchone()
        return dict(row) if row else None


def db_verify_user(user_id: int):
    """Mark user as verified and clear verification token."""
    with db_connect() as con:
        con.execute(
            "UPDATE users SET verified=1, verification_token=NULL, verification_token_expires=NULL WHERE id=?",
            (user_id,)
        )
        con.commit()


def db_update_last_login(user_id: int):
    """Update user's last login timestamp."""
    now = int(time.time())
    with db_connect() as con:
        con.execute("UPDATE users SET last_login_at=? WHERE id=?", (now, user_id))
        con.commit()


def db_set_remember_token(user_id: int, token: str):
    """Set remember-me token for user."""
    with db_connect() as con:
        con.execute("UPDATE users SET remember_token=? WHERE id=?", (token, user_id))
        con.commit()


def db_clear_remember_token(user_id: int):
    """Clear remember-me token for user."""
    with db_connect() as con:
        con.execute("UPDATE users SET remember_token=NULL WHERE id=?", (user_id,))
        con.commit()


def db_get_user_by_remember_token(token: str) -> Optional[Dict[str, Any]]:
    """Get user by remember-me token."""
    with db_connect() as con:
        row = con.execute("SELECT * FROM users WHERE remember_token=?", (token,)).fetchone()
        return dict(row) if row else None


def db_list_active_rooms(hours: int = 24) -> List[Dict[str, Any]]:
    """List rooms with activity in the last N hours."""
    cutoff = int(time.time()) - (hours * 3600)
    with db_connect() as con:
        rows = con.execute(
            "SELECT * FROM rooms WHERE last_activity_at > ? ORDER BY last_activity_at DESC",
            (cutoff,)
        ).fetchall()
        return [dict(row) for row in rows]


def db_update_room_activity(room_name: str, user_id: Optional[int] = None):
    """Update or create room activity record."""
    now = int(time.time())
    with db_connect() as con:
        existing = con.execute("SELECT name FROM rooms WHERE name=?", (room_name,)).fetchone()
        if existing:
            con.execute("UPDATE rooms SET last_activity_at=? WHERE name=?", (now, room_name))
        else:
            con.execute(
                "INSERT INTO rooms (name, created_by, created_at, last_activity_at) VALUES (?,?,?,?)",
                (room_name, user_id, now, now)
            )
        con.commit()


def db_set_password_reset_token(user_id: int, token: str, expires: int):
    """Set password reset token for user."""
    with db_connect() as con:
        con.execute(
            "UPDATE users SET reset_token=?, reset_token_expires=? WHERE id=?",
            (token, expires, user_id)
        )
        con.commit()


def db_get_user_by_reset_token(token: str) -> Optional[Dict[str, Any]]:
    """Get user by password reset token."""
    with db_connect() as con:
        row = con.execute("SELECT * FROM users WHERE reset_token=?", (token,)).fetchone()
        return dict(row) if row else None


def db_update_password(user_id: int, password_hash: str):
    """Update user's password and clear reset token."""
    with db_connect() as con:
        con.execute(
            "UPDATE users SET password_hash=?, reset_token=NULL, reset_token_expires=NULL WHERE id=?",
            (password_hash, user_id)
        )
        con.commit()


# ---- Admin functions ----

def db_list_all_users() -> List[Dict[str, Any]]:
    """List all users for admin."""
    with db_connect() as con:
        rows = con.execute(
            "SELECT id, email, display_name, verified, created_at, last_login_at FROM users ORDER BY created_at DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def db_get_user_stats() -> Dict[str, int]:
    """Get user statistics."""
    with db_connect() as con:
        total = con.execute("SELECT COUNT(*) as n FROM users").fetchone()["n"]
        verified = con.execute("SELECT COUNT(*) as n FROM users WHERE verified=1").fetchone()["n"]
        return {
            "total": total,
            "verified": verified,
            "unverified": total - verified
        }


def db_delete_user(user_id: int) -> bool:
    """Delete a user by ID. Returns True if deleted."""
    with db_connect() as con:
        cursor = con.execute("DELETE FROM users WHERE id=?", (user_id,))
        con.commit()
        return cursor.rowcount > 0


def db_set_verification_token(user_id: int, token: str, expires: int):
    """Set new verification token for resending verification email."""
    with db_connect() as con:
        con.execute(
            "UPDATE users SET verification_token=?, verification_token_expires=?, verified=0 WHERE id=?",
            (token, expires, user_id)
        )
        con.commit()


def db_manually_verify_user(user_id: int) -> bool:
    """Manually verify a user without email. Returns True if updated."""
    with db_connect() as con:
        cursor = con.execute(
            "UPDATE users SET verified=1, verification_token=NULL, verification_token_expires=NULL WHERE id=? AND verified=0",
            (user_id,)
        )
        con.commit()
        return cursor.rowcount > 0


def db_delete_room(room_name: str) -> bool:
    """Delete a room from the database. Returns True if deleted."""
    with db_connect() as con:
        cursor = con.execute("DELETE FROM rooms WHERE name=?", (room_name,))
        con.commit()
        return cursor.rowcount > 0
