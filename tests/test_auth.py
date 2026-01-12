"""Tests for authentication and admin routes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import io  # noqa: E402
import json  # noqa: E402

from werkzeug.security import generate_password_hash  # noqa: E402

from app import app, db_add_puzzles, db_connect, db_get_pack_id  # noqa: E402
from db_auth import (  # noqa: E402
    db_create_user,
    db_delete_user,
    db_get_user_by_email,
    db_get_user_stats,
    db_init_auth,
    db_list_active_rooms,
    db_list_all_users,
    db_manually_verify_user,
    db_update_room_activity,
    db_verify_user,
)


class TestAuthDatabaseFunctions:
    """Tests for db_auth.py functions."""

    def test_db_init_auth(self):
        """Test that auth tables are created."""
        db_init_auth()
        with db_connect() as con:
            # Check users table exists
            result = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
            ).fetchone()
            assert result is not None

            # Check rooms table exists
            result = con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='rooms'"
            ).fetchone()
            assert result is not None

    def test_db_create_user(self):
        """Test user creation."""
        db_init_auth()
        email = "test_create@example.com"
        password_hash = generate_password_hash("testpass")
        user_id = db_create_user(email, password_hash, "Test User", "token123", 9999999999)
        assert user_id > 0

        user = db_get_user_by_email(email)
        assert user is not None
        assert user["display_name"] == "Test User"
        assert user["verified"] == 0

        # Cleanup
        db_delete_user(user_id)

    def test_db_verify_user(self):
        """Test manual user verification."""
        db_init_auth()
        email = "test_verify@example.com"
        password_hash = generate_password_hash("testpass")
        user_id = db_create_user(email, password_hash, "Verify User", "token456", 9999999999)

        # Verify user
        db_verify_user(user_id)
        user = db_get_user_by_email(email)
        assert user["verified"] == 1
        assert user["verification_token"] is None

        # Cleanup
        db_delete_user(user_id)

    def test_db_list_all_users(self):
        """Test listing all users."""
        db_init_auth()
        users = db_list_all_users()
        assert isinstance(users, list)

    def test_db_get_user_stats(self):
        """Test user statistics."""
        db_init_auth()
        stats = db_get_user_stats()
        assert "total" in stats
        assert "verified" in stats
        assert "unverified" in stats
        assert stats["total"] == stats["verified"] + stats["unverified"]

    def test_db_manually_verify_user(self):
        """Test manual verification."""
        db_init_auth()
        email = "test_manual_verify@example.com"
        password_hash = generate_password_hash("testpass")
        user_id = db_create_user(email, password_hash, "Manual Verify", "token789", 9999999999)

        # Should return True on first verify
        result = db_manually_verify_user(user_id)
        assert result is True

        # Should return False when already verified
        result = db_manually_verify_user(user_id)
        assert result is False

        # Cleanup
        db_delete_user(user_id)


class TestAuthRoutes:
    """Tests for auth blueprint routes."""

    def test_login_page_get(self):
        """Test GET /auth/login returns login page."""
        with app.test_client() as client:
            response = client.get("/auth/login")
            assert response.status_code == 200
            assert b"Login" in response.data

    def test_register_page_get(self):
        """Test GET /auth/register returns register page."""
        with app.test_client() as client:
            response = client.get("/auth/register")
            assert response.status_code == 200
            assert b"Register" in response.data or b"Create Account" in response.data

    def test_login_missing_fields(self):
        """Test login with missing fields."""
        with app.test_client() as client:
            response = client.post(
                "/auth/login",
                json={"email": ""},
                content_type="application/json"
            )
            assert response.status_code == 400
            data = response.get_json()
            assert data["ok"] is False

    def test_login_invalid_credentials(self):
        """Test login with invalid credentials."""
        with app.test_client() as client:
            response = client.post(
                "/auth/login",
                json={"email": "nonexistent@example.com", "password": "wrongpass"},
                content_type="application/json"
            )
            assert response.status_code == 401
            data = response.get_json()
            assert data["ok"] is False

    def test_register_validation(self):
        """Test registration validation."""
        with app.test_client() as client:
            # Invalid email
            response = client.post(
                "/auth/register",
                json={"email": "invalid", "password": "password123", "display_name": "Test"},
                content_type="application/json"
            )
            assert response.status_code == 400

            # Short password
            response = client.post(
                "/auth/register",
                json={"email": "valid@example.com", "password": "short", "display_name": "Test"},
                content_type="application/json"
            )
            assert response.status_code == 400

            # Short display name
            response = client.post(
                "/auth/register",
                json={"email": "valid@example.com", "password": "password123", "display_name": "X"},
                content_type="application/json"
            )
            assert response.status_code == 400

    def test_me_not_logged_in(self):
        """Test /auth/me when not logged in."""
        with app.test_client() as client:
            response = client.get("/auth/me")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is False
            assert data["user"] is None

    def test_logout(self):
        """Test logout endpoint."""
        with app.test_client() as client:
            response = client.post("/auth/logout")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True


class TestAdminRoutes:
    """Tests for admin routes requiring host authentication."""

    def _get_host_session(self, client):
        """Helper to authenticate as host."""
        # First login as a user (create one if needed)
        db_init_auth()
        email = "admin_test@example.com"
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Admin Test", "admintoken", 9999999999)
            db_verify_user(user_id)

        # Login
        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
            content_type="application/json"
        )

        # Authenticate as host
        response = client.post(
            "/auth/admin/verify-host",
            json={"code": "testcode"},  # From conftest.py
            content_type="application/json"
        )
        return response

    def test_admin_page_requires_login(self):
        """Test admin page requires login."""
        with app.test_client() as client:
            response = client.get("/auth/admin")
            # Should redirect to login
            assert response.status_code == 302

    def test_verify_host_invalid_code(self):
        """Test host verification with invalid code."""
        with app.test_client() as client:
            # First need to be logged in
            db_init_auth()
            email = "host_invalid@example.com"
            user = db_get_user_by_email(email)
            if not user:
                password_hash = generate_password_hash("testpass123")
                user_id = db_create_user(email, password_hash, "Host Invalid", "hosttoken", 9999999999)
                db_verify_user(user_id)

            client.post(
                "/auth/login",
                json={"email": email, "password": "testpass123"},
                content_type="application/json"
            )

            response = client.post(
                "/auth/admin/verify-host",
                json={"code": "wrongcode"},
                content_type="application/json"
            )
            assert response.status_code == 401
            data = response.get_json()
            assert data["ok"] is False

    def test_verify_host_valid_code(self):
        """Test host verification with valid code."""
        with app.test_client() as client:
            response = self._get_host_session(client)
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

    def test_admin_users_requires_host(self):
        """Test admin users endpoint requires host auth."""
        with app.test_client() as client:
            # Login but don't authenticate as host
            db_init_auth()
            email = "users_nohost@example.com"
            user = db_get_user_by_email(email)
            if not user:
                password_hash = generate_password_hash("testpass123")
                user_id = db_create_user(email, password_hash, "No Host", "nohosttoken", 9999999999)
                db_verify_user(user_id)

            client.post(
                "/auth/login",
                json={"email": email, "password": "testpass123"},
                content_type="application/json"
            )

            response = client.get("/auth/admin/users")
            assert response.status_code == 403

    def test_admin_users_list(self):
        """Test listing users as admin."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.get("/auth/admin/users")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "users" in data
            assert "stats" in data

    def test_admin_rooms_list(self):
        """Test listing rooms as admin."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.get("/auth/admin/rooms")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "rooms" in data

    def test_admin_verify_user(self):
        """Test manually verifying a user."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create unverified user
            db_init_auth()
            email = "unverified_user@example.com"
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Unverified", "unvtoken", 9999999999)

            response = client.post(f"/auth/admin/users/{user_id}/verify")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

            # Verify the user is now verified
            user = db_get_user_by_email(email)
            assert user["verified"] == 1

            # Cleanup
            db_delete_user(user_id)

    def test_admin_delete_user(self):
        """Test deleting a user."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create user to delete
            db_init_auth()
            email = "delete_me@example.com"
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Delete Me", "deletetoken", 9999999999)

            response = client.delete(f"/auth/admin/users/{user_id}")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

            # Verify user is deleted
            user = db_get_user_by_email(email)
            assert user is None

    def test_admin_delete_user_not_found(self):
        """Test deleting non-existent user."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.delete("/auth/admin/users/99999")
            assert response.status_code == 404

    def test_logout_host(self):
        """Test logging out of host mode."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Logout host
            response = client.post("/auth/admin/logout-host")
            assert response.status_code == 200

            # Should no longer have host access
            response = client.get("/auth/admin/users")
            assert response.status_code == 403


class TestAdminPackRoutes:
    """Tests for admin pack management routes."""

    def _get_host_session(self, client):
        """Helper to authenticate as host."""
        db_init_auth()
        email = "pack_admin@example.com"
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Pack Admin", "packtoken", 9999999999)
            db_verify_user(user_id)

        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
            content_type="application/json"
        )

        client.post(
            "/auth/admin/verify-host",
            json={"code": "testcode"},
            content_type="application/json"
        )

    def test_admin_packs_list(self):
        """Test listing packs."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.get("/auth/admin/packs")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "packs" in data

    def test_admin_create_pack(self):
        """Test creating a pack."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/packs",
                json={
                    "name": "Test Admin Pack",
                    "puzzles": "Category One | Answer One\nCategory Two | Answer Two"
                },
                content_type="application/json"
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert data["added"] == 2

    def test_admin_create_pack_no_name(self):
        """Test creating pack without name."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/packs",
                json={"name": "", "puzzles": "Cat | Ans"},
                content_type="application/json"
            )
            assert response.status_code == 400

    def test_admin_create_pack_no_puzzles(self):
        """Test creating pack without puzzles."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/packs",
                json={"name": "Empty Pack", "puzzles": ""},
                content_type="application/json"
            )
            assert response.status_code == 400

    def test_admin_create_pack_invalid_format(self):
        """Test creating pack with invalid puzzle format."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/packs",
                json={"name": "Bad Format Pack", "puzzles": "No pipe character"},
                content_type="application/json"
            )
            assert response.status_code == 400

    def test_admin_import_packs(self):
        """Test importing packs from JSON."""
        with app.test_client() as client:
            self._get_host_session(client)

            payload = {
                "packs": [
                    {
                        "name": "Import Admin Pack",
                        "puzzles": [
                            {"category": "Cat1", "answer": "Ans1"},
                            {"category": "Cat2", "answer": "Ans2"}
                        ]
                    }
                ]
            }

            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/auth/admin/packs/import",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            assert result["ok"] is True
            assert result["total_added"] == 2

    def test_admin_import_packs_no_file(self):
        """Test import without file."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post("/auth/admin/packs/import")
            assert response.status_code == 400

    def test_admin_import_packs_invalid_json(self):
        """Test import with invalid JSON."""
        with app.test_client() as client:
            self._get_host_session(client)

            data = io.BytesIO(b"not valid json")
            response = client.post(
                "/auth/admin/packs/import",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 400

    def test_admin_delete_pack(self):
        """Test deleting a pack."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create pack to delete
            pack_id = db_get_pack_id("Pack To Delete")
            db_add_puzzles([("Cat", "Ans")], pack_id)

            response = client.delete(f"/auth/admin/packs/{pack_id}")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

    def test_admin_delete_pack_not_found(self):
        """Test deleting non-existent pack."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.delete("/auth/admin/packs/99999")
            assert response.status_code == 404


class TestAdminConfigRoutes:
    """Tests for admin config routes."""

    def _get_host_session(self, client):
        """Helper to authenticate as host."""
        db_init_auth()
        email = "config_admin@example.com"
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Config Admin", "configtoken", 9999999999)
            db_verify_user(user_id)

        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
            content_type="application/json"
        )

        client.post(
            "/auth/admin/verify-host",
            json={"code": "testcode"},
            content_type="application/json"
        )

    def test_admin_get_config(self):
        """Test getting room config."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.get("/auth/admin/config/test_config_room")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "config" in data
            assert "vowel_cost" in data["config"]

    def test_admin_set_config(self):
        """Test setting room config."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/config/test_config_room",
                json={
                    "vowel_cost": 300,
                    "final_seconds": 45,
                    "final_jackpot": 15000,
                    "prize_cash_csv": "500,1000,1500"
                },
                content_type="application/json"
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

            # Verify config was saved
            response = client.get("/auth/admin/config/test_config_room")
            data = response.get_json()
            assert data["config"]["vowel_cost"] == 300
            assert data["config"]["final_seconds"] == 45

    def test_admin_set_config_with_pack(self):
        """Test setting config with active pack."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create a pack
            pack_id = db_get_pack_id("Config Test Pack")

            response = client.post(
                "/auth/admin/config/test_pack_config_room",
                json={"active_pack_id": pack_id},
                content_type="application/json"
            )
            assert response.status_code == 200

            # Verify
            response = client.get("/auth/admin/config/test_pack_config_room")
            data = response.get_json()
            assert data["config"]["active_pack_id"] == pack_id

    def test_admin_set_config_clear_pack(self):
        """Test clearing active pack."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post(
                "/auth/admin/config/test_clear_pack_room",
                json={"active_pack_id": ""},
                content_type="application/json"
            )
            assert response.status_code == 200

            response = client.get("/auth/admin/config/test_clear_pack_room")
            data = response.get_json()
            assert data["config"]["active_pack_id"] is None


class TestEmailVerification:
    """Tests for email verification route."""

    def test_verify_valid_token(self):
        """Test verifying email with valid token."""
        db_init_auth()
        email = "verify_valid@example.com"
        password_hash = generate_password_hash("testpass123")
        token = "valid_test_token_123"
        expires = 9999999999  # Far future
        user_id = db_create_user(email, password_hash, "Verify Valid", token, expires)

        with app.test_client() as client:
            response = client.get(f"/auth/verify/{token}")
            assert response.status_code == 200
            assert b"verified successfully" in response.data.lower()

        # Verify user is now verified
        user = db_get_user_by_email(email)
        assert user["verified"] == 1

        # Cleanup
        db_delete_user(user_id)

    def test_verify_invalid_token(self):
        """Test verifying email with invalid token."""
        with app.test_client() as client:
            response = client.get("/auth/verify/invalid_token_xyz")
            assert response.status_code == 200
            assert b"invalid" in response.data.lower() or b"expired" in response.data.lower()

    def test_verify_expired_token(self):
        """Test verifying email with expired token."""
        db_init_auth()
        email = "verify_expired@example.com"
        password_hash = generate_password_hash("testpass123")
        token = "expired_test_token_456"
        expires = 1  # Already expired (1970)
        user_id = db_create_user(email, password_hash, "Verify Expired", token, expires)

        with app.test_client() as client:
            response = client.get(f"/auth/verify/{token}")
            assert response.status_code == 200
            assert b"expired" in response.data.lower()

        # Cleanup
        db_delete_user(user_id)


class TestLobbyAndRooms:
    """Tests for lobby and rooms endpoints."""

    def _login_user(self, client, email="lobby_user@example.com"):
        """Helper to create and login a verified user."""
        db_init_auth()
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Lobby User", "lobbytoken", 9999999999)
            db_verify_user(user_id)

        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
            content_type="application/json"
        )

    def test_lobby_requires_login(self):
        """Test lobby page requires login."""
        with app.test_client() as client:
            response = client.get("/auth/lobby")
            # Should redirect to login
            assert response.status_code == 302

    def test_lobby_page(self):
        """Test lobby page loads for logged-in user."""
        with app.test_client() as client:
            self._login_user(client)

            response = client.get("/auth/lobby")
            assert response.status_code == 200

    def test_rooms_requires_login(self):
        """Test rooms API requires login."""
        with app.test_client() as client:
            response = client.get("/auth/rooms")
            assert response.status_code == 302

    def test_rooms_list(self):
        """Test rooms API returns list."""
        with app.test_client() as client:
            self._login_user(client)

            response = client.get("/auth/rooms")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "rooms" in data

    def test_rooms_with_activity(self):
        """Test rooms API includes recently active rooms."""
        db_init_auth()

        # Create room activity
        db_update_room_activity("test_lobby_room")

        with app.test_client() as client:
            self._login_user(client)

            response = client.get("/auth/rooms")
            data = response.get_json()
            assert data["ok"] is True

            # Check room is in list
            room_names = [r["name"] for r in data["rooms"]]
            assert "test_lobby_room" in room_names


class TestResendVerification:
    """Tests for resend verification email."""

    def _get_host_session(self, client):
        """Helper to authenticate as host."""
        db_init_auth()
        email = "resend_admin@example.com"
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Resend Admin", "resendtoken", 9999999999)
            db_verify_user(user_id)

        client.post(
            "/auth/login",
            json={"email": email, "password": "testpass123"},
            content_type="application/json"
        )

        client.post(
            "/auth/admin/verify-host",
            json={"code": "testcode"},
            content_type="application/json"
        )

    def test_resend_to_unverified_user(self):
        """Test resending verification to unverified user."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create unverified user
            db_init_auth()
            email = "resend_unverified@example.com"
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Unverified", "oldtoken", 9999999999)

            response = client.post(f"/auth/admin/users/{user_id}/resend")
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

            # Cleanup
            db_delete_user(user_id)

    def test_resend_to_verified_user(self):
        """Test resending verification to already verified user fails."""
        with app.test_client() as client:
            self._get_host_session(client)

            # Create verified user
            db_init_auth()
            email = "resend_verified@example.com"
            password_hash = generate_password_hash("testpass123")
            user_id = db_create_user(email, password_hash, "Verified", "vertoken", 9999999999)
            db_verify_user(user_id)

            response = client.post(f"/auth/admin/users/{user_id}/resend")
            assert response.status_code == 400
            data = response.get_json()
            assert data["ok"] is False
            assert "already verified" in data["error"].lower()

            # Cleanup
            db_delete_user(user_id)

    def test_resend_to_nonexistent_user(self):
        """Test resending verification to nonexistent user."""
        with app.test_client() as client:
            self._get_host_session(client)

            response = client.post("/auth/admin/users/99999/resend")
            assert response.status_code == 404


class TestFullAuthFlows:
    """Tests for complete authentication flows."""

    def test_successful_registration(self):
        """Test successful user registration."""
        db_init_auth()
        email = "new_user_flow@example.com"

        # Clean up if exists
        user = db_get_user_by_email(email)
        if user:
            db_delete_user(user["id"])

        with app.test_client() as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": "securepass123",
                    "display_name": "New User"
                },
                content_type="application/json"
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True

        # Verify user was created
        user = db_get_user_by_email(email)
        assert user is not None
        assert user["display_name"] == "New User"
        assert user["verified"] == 0  # Not yet verified

        # Cleanup
        db_delete_user(user["id"])

    def test_successful_login(self):
        """Test successful login with verified user."""
        db_init_auth()
        email = "login_flow@example.com"
        password = "testpass123"

        # Create verified user
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash(password)
            user_id = db_create_user(email, password_hash, "Login User", "logintoken", 9999999999)
            db_verify_user(user_id)

        with app.test_client() as client:
            response = client.post(
                "/auth/login",
                json={"email": email, "password": password},
                content_type="application/json"
            )
            assert response.status_code == 200
            data = response.get_json()
            assert data["ok"] is True
            assert "user" in data
            assert data["user"]["display_name"] == "Login User"

    def test_login_unverified_fails(self):
        """Test login fails for unverified user."""
        db_init_auth()
        email = "unverified_login@example.com"
        password = "testpass123"

        # Create unverified user
        user = db_get_user_by_email(email)
        if user:
            db_delete_user(user["id"])

        password_hash = generate_password_hash(password)
        user_id = db_create_user(email, password_hash, "Unverified Login", "unveriftoken", 9999999999)

        with app.test_client() as client:
            response = client.post(
                "/auth/login",
                json={"email": email, "password": password},
                content_type="application/json"
            )
            assert response.status_code == 403
            data = response.get_json()
            assert data["ok"] is False
            assert "verify" in data["error"].lower() or "verified" in data["error"].lower()

        # Cleanup
        db_delete_user(user_id)

    def test_duplicate_registration(self):
        """Test registration fails for existing email."""
        db_init_auth()
        email = "duplicate_reg@example.com"

        # Create existing user
        user = db_get_user_by_email(email)
        if not user:
            password_hash = generate_password_hash("testpass123")
            db_create_user(email, password_hash, "Existing User", "existtoken", 9999999999)

        with app.test_client() as client:
            response = client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": "newpass123",
                    "display_name": "Duplicate"
                },
                content_type="application/json"
            )
            assert response.status_code == 409  # Conflict
            data = response.get_json()
            assert data["ok"] is False


class TestRoomActivityDatabase:
    """Tests for room activity database functions."""

    def test_db_update_room_activity(self):
        """Test updating room activity."""
        db_init_auth()
        room_name = "db_activity_test_room"

        db_update_room_activity(room_name)

        rooms = db_list_active_rooms(hours=1)
        room_names = [r["name"] for r in rooms]
        assert room_name in room_names

    def test_db_update_room_activity_with_user(self):
        """Test updating room activity with user ID."""
        db_init_auth()
        room_name = "db_activity_user_room"

        # Create a user
        email = "room_activity_user@example.com"
        password_hash = generate_password_hash("testpass123")
        user_id = db_create_user(email, password_hash, "Activity User", "acttoken", 9999999999)

        db_update_room_activity(room_name, user_id=user_id)

        rooms = db_list_active_rooms(hours=1)
        room_names = [r["name"] for r in rooms]
        assert room_name in room_names

        # Cleanup
        db_delete_user(user_id)

    def test_db_list_active_rooms(self):
        """Test listing active rooms."""
        db_init_auth()

        rooms = db_list_active_rooms(hours=24)
        assert isinstance(rooms, list)

        # Each room should have expected fields
        if rooms:
            room = rooms[0]
            assert "name" in room
            assert "last_activity_at" in room
