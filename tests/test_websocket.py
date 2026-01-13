import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import GAMES, app, socketio  # noqa: E402
from db_auth import db_create_user, db_init_auth, db_verify_user  # noqa: E402

# Initialize auth tables for tests
db_init_auth()

# Counter for unique test users
_test_user_counter = 0


def create_test_user_session(flask_client, display_name="TestPlayer"):
    """Create a test user and set up session for authenticated testing."""
    global _test_user_counter
    _test_user_counter += 1
    email = f"test{_test_user_counter}@test.com"

    # Create and verify user
    try:
        user_id = db_create_user(email, "hashedpw", display_name, "token", 9999999999)
        db_verify_user(user_id)
    except Exception:
        # User might already exist, that's fine for tests
        from db_auth import db_get_user_by_email

        user = db_get_user_by_email(email)
        user_id = user["id"] if user else 1

    # Set up session
    with flask_client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["display_name"] = display_name

    return user_id


class TestWebSocketConnection:
    def setup_method(self):
        """Set up test client before each test."""
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)

    def teardown_method(self):
        """Disconnect client after each test."""
        if self.client.is_connected():
            self.client.disconnect()

    def test_connect(self):
        assert self.client.is_connected()

    def test_join_room(self):
        self.client.emit("join", {"room": "test_room"})
        received = self.client.get_received()

        # Should receive state event
        state_events = [r for r in received if r["name"] == "state"]
        assert len(state_events) >= 1
        assert state_events[0]["args"][0]["room"] == "test_room"

    def test_join_creates_game_state(self):
        self.client.emit("join", {"room": "new_room"})
        self.client.get_received()

        assert "new_room" in GAMES
        assert len(GAMES["new_room"].players) == 0  # No players until someone joins

    def test_disconnect_releases_claims(self):
        # Need a new client with auth session set up before connection
        flask_client = app.test_client()
        create_test_user_session(flask_client, "Test")
        client = socketio.test_client(app, flask_test_client=flask_client)

        # Join room and join game as player
        client.emit("join", {"room": "disconnect_test"})
        client.get_received()

        client.emit("join_game", {"room": "disconnect_test"})
        client.get_received()

        # Verify player is claimed
        game = GAMES["disconnect_test"]
        assert len(game.players) == 1
        assert game.players[0].claimed_sid is not None

        # Disconnect
        client.disconnect()

        # Player's claimed_sid should be released
        assert game.players[0].claimed_sid is None


class TestHostClaiming:
    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.client = socketio.test_client(app, flask_test_client=app.test_client())
        self.client.emit("join", {"room": "host_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_claim_host_with_correct_code(self):
        self.client.emit("claim_host", {"room": "host_test", "code": "testcode"})
        received = self.client.get_received()

        # Should receive host_granted and toast
        host_events = [r for r in received if r["name"] == "host_granted"]
        assert len(host_events) >= 1
        assert host_events[0]["args"][0]["granted"] is True

        # Game should have host_sid set
        assert GAMES["host_test"].host_sid is not None

    def test_claim_host_with_wrong_code(self):
        self.client.emit("claim_host", {"room": "host_test", "code": "wrongcode"})
        received = self.client.get_received()

        host_events = [r for r in received if r["name"] == "host_granted"]
        assert len(host_events) >= 1
        assert host_events[0]["args"][0]["granted"] is False

        assert GAMES["host_test"].host_sid is None

    def test_release_host(self):
        # First claim host
        self.client.emit("claim_host", {"room": "host_test", "code": "testcode"})
        self.client.get_received()

        # Then release
        self.client.emit("release_host", {"room": "host_test"})
        received = self.client.get_received()

        host_events = [r for r in received if r["name"] == "host_granted"]
        assert len(host_events) >= 1
        assert host_events[0]["args"][0]["granted"] is False

        assert GAMES["host_test"].host_sid is None


class TestPlayerClaiming:
    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Alice")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "player_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_join_game(self):
        self.client.emit("join_game", {"room": "player_test"})
        received = self.client.get_received()

        # Should receive "you" event with player index
        you_events = [r for r in received if r["name"] == "you"]
        assert len(you_events) >= 1
        assert you_events[0]["args"][0]["player_idx"] == 0  # First player

        # Player should be added and claimed
        game = GAMES["player_test"]
        assert len(game.players) >= 1
        assert game.players[0].claimed_sid is not None
        assert game.players[0].name == "Alice"

    def test_leave_game(self):
        # First join
        self.client.emit("join_game", {"room": "player_test"})
        self.client.get_received()

        game = GAMES["player_test"]
        assert len(game.players) == 1

        # Then leave
        self.client.emit("leave_game", {"room": "player_test"})
        received = self.client.get_received()

        you_events = [r for r in received if r["name"] == "you"]
        assert len(you_events) >= 1
        assert you_events[0]["args"][0]["player_idx"] is None

        # Player should be removed
        assert len(game.players) == 0


class TestGameActions:
    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "game_test"})
        self.client.get_received()

        # Join game as player (creates and claims player 0)
        self.client.emit("join_game", {"room": "game_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_spin_as_active_player(self):
        self.client.emit("spin", {"room": "game_test"})
        received = self.client.get_received()

        # Should receive state update
        state_events = [r for r in received if r["name"] == "state"]
        assert len(state_events) >= 1

        game = GAMES["game_test"]
        # Wheel should have been spun (index set)
        assert game.wheel_index is not None or game.last_spin_index is not None

    def test_spin_as_non_active_player(self):
        # Create a second client that joins as a different player
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "Other")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "game_test"})
        client2.get_received()
        client2.emit("join_game", {"room": "game_test"})
        client2.get_received()

        # Second player tries to spin (but first player is active)
        client2.emit("spin", {"room": "game_test"})
        received = client2.get_received()

        # Should receive toast about not being active player
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("active player" in str(t["args"]).lower() for t in toast_events)

        client2.disconnect()

    def test_guess_vowel_without_funds(self):
        game = GAMES["game_test"]
        game.players[0].round_bank = 0

        # Spin first to get a wedge
        game.current_wedge = 500

        self.client.emit("guess", {"room": "game_test", "letter": "A"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("vowel" in str(t["args"]).lower() for t in toast_events)

    def test_guess_consonant_without_spin(self):
        game = GAMES["game_test"]
        game.current_wedge = None

        self.client.emit("guess", {"room": "game_test", "letter": "T"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("spin" in str(t["args"]).lower() for t in toast_events)

    def test_guess_consonant_after_spin(self):
        game = GAMES["game_test"]
        game.set_puzzle(1, "Test", "HELLO WORLD")
        game.current_wedge = 500  # Must be after set_puzzle (which clears turn state)

        self.client.emit("guess", {"room": "game_test", "letter": "L"})
        self.client.get_received()

        # L appears 3 times in HELLO WORLD
        assert "L" in game.revealed
        assert "L" in game.used_letters

    def test_solve_correct(self):
        game = GAMES["game_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.players[0].round_bank = 1000

        self.client.emit("solve", {"room": "game_test", "attempt": "HELLO"})
        self.client.get_received()

        # Player should have won the round
        assert game.players[0].total == 1000
        assert game.players[0].round_bank == 0

    def test_solve_incorrect(self):
        # Need at least 2 players to test turn advancement
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "Player2")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "game_test"})
        client2.get_received()
        client2.emit("join_game", {"room": "game_test"})
        client2.get_received()

        game = GAMES["game_test"]
        game.set_puzzle(1, "Test", "HELLO")
        initial_idx = game.active_idx

        self.client.emit("solve", {"room": "game_test", "attempt": "WRONG"})
        self.client.get_received()

        # Turn should advance to next player
        assert game.active_idx != initial_idx
        client2.disconnect()


class TestHostOnlyActions:
    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.client = socketio.test_client(app, flask_test_client=app.test_client())
        self.client.emit("join", {"room": "host_only_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_new_puzzle_without_host(self):
        self.client.emit("new_puzzle", {"room": "host_only_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("host" in str(t["args"]).lower() for t in toast_events)

    def test_new_puzzle_as_host(self):
        # Claim host first
        self.client.emit("claim_host", {"room": "host_only_test", "code": "testcode"})
        self.client.get_received()

        game = GAMES["host_only_test"]
        old_puzzle_id = game.puzzle.get("id")

        self.client.emit("new_puzzle", {"room": "host_only_test"})
        self.client.get_received()

        # Puzzle should have changed (or toast about no puzzles)
        # Since DB has puzzles, it should change
        new_puzzle_id = game.puzzle.get("id")
        assert new_puzzle_id != old_puzzle_id or old_puzzle_id is None

    def test_new_game_as_host(self):
        # Claim host
        self.client.emit("claim_host", {"room": "host_only_test", "code": "testcode"})
        self.client.get_received()

        # Join game to create a player (need authenticated user)
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "TestPlayer")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "host_only_test"})
        client2.get_received()
        client2.emit("join_game", {"room": "host_only_test"})
        client2.get_received()

        game = GAMES["host_only_test"]
        game.players[0].total = 5000

        self.client.emit("new_game", {"room": "host_only_test"})
        self.client.get_received()

        # Scores should be reset
        assert game.players[0].total == 0
        client2.disconnect()


class TestPackManagement:
    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.client = socketio.test_client(app, flask_test_client=app.test_client())
        self.client.emit("join", {"room": "pack_test"})
        self.client.get_received()
        # Claim host
        self.client.emit("claim_host", {"room": "pack_test", "code": "testcode"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_list_packs(self):
        self.client.emit("list_packs", {"room": "pack_test"})
        received = self.client.get_received()

        pack_events = [r for r in received if r["name"] == "packs"]
        assert len(pack_events) >= 1
        assert "packs" in pack_events[0]["args"][0]

    def test_load_pack(self):
        pack_data = "Category|ANSWER ONE\nCategory|ANSWER TWO"
        self.client.emit("load_pack", {"room": "pack_test", "pack_name": "Test Pack", "text": pack_data})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("2 puzzles" in str(t["args"]) for t in toast_events)


class TestSpecialWedges:
    """Tests for FREE PLAY and PRIZE wedge game logic."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "wedge_test"})
        self.client.get_received()
        # Join game as player
        self.client.emit("join_game", {"room": "wedge_test"})
        self.client.get_received()
        # Add second player for turn advancement tests
        self.flask_client2 = app.test_client()
        create_test_user_session(self.flask_client2, "Player2")
        self.client2 = socketio.test_client(app, flask_test_client=self.flask_client2)
        self.client2.emit("join", {"room": "wedge_test"})
        self.client2.get_received()
        self.client2.emit("join_game", {"room": "wedge_test"})
        self.client2.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()
        if self.client2.is_connected():
            self.client2.disconnect()

    def test_free_play_hit_letter(self):
        """FREE PLAY wedge: hit a letter, stay on turn."""
        game = GAMES["wedge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = "FREE PLAY"

        initial_idx = game.active_idx
        self.client.emit("guess", {"room": "wedge_test", "letter": "L"})
        received = self.client.get_received()

        assert "L" in game.revealed
        assert game.active_idx == initial_idx  # Same player's turn
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("free play" in str(t["args"]).lower() for t in toast_events)

    def test_free_play_miss_letter(self):
        """FREE PLAY wedge: miss a letter, keep turn (FREE PLAY benefit)."""
        game = GAMES["wedge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = "FREE PLAY"

        initial_idx = game.active_idx
        self.client.emit("guess", {"room": "wedge_test", "letter": "Z"})
        received = self.client.get_received()

        assert "Z" not in game.revealed
        assert game.active_idx == initial_idx  # FREE PLAY keeps turn on miss
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("no z" in str(t["args"]).lower() for t in toast_events)

    def test_prize_wedge_hit_letter(self):
        """PRIZE wedge: hit a letter, win the prize."""
        game = GAMES["wedge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = {"type": "PRIZE", "name": "GIFT CARD"}
        game.last_spin_index = 0
        game.wheel_slots[0] = {"type": "PRIZE", "name": "GIFT CARD"}

        self.client.emit("guess", {"room": "wedge_test", "letter": "L"})
        received = self.client.get_received()

        assert "L" in game.revealed
        # Player should have prize in round_prizes
        assert len(game.players[0].round_prizes) == 1
        assert game.players[0].round_prizes[0]["name"] == "GIFT CARD"
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("prize banked" in str(t["args"]).lower() for t in toast_events)

    def test_prize_wedge_miss_letter(self):
        """PRIZE wedge: miss a letter, lose prize and turn."""
        game = GAMES["wedge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = {"type": "PRIZE", "name": "GIFT CARD"}

        initial_idx = game.active_idx
        self.client.emit("guess", {"room": "wedge_test", "letter": "Z"})
        received = self.client.get_received()

        assert "Z" not in game.revealed
        assert game.active_idx != initial_idx  # Turn advances
        assert len(game.players[0].round_prizes) == 0  # No prize
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("lost the prize" in str(t["args"]).lower() for t in toast_events)

    def test_prize_wedge_no_duplicate(self):
        """PRIZE wedge: can't win same prize twice."""
        game = GAMES["wedge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.players[0].round_prizes = [{"name": "GIFT CARD", "value": 500}]
        game.current_wedge = {"type": "PRIZE", "name": "GIFT CARD"}
        game.last_spin_index = 0
        game.wheel_slots[0] = {"type": "PRIZE", "name": "GIFT CARD"}

        self.client.emit("guess", {"room": "wedge_test", "letter": "L"})
        self.client.get_received()

        # Should still only have one prize (no duplicate)
        assert len(game.players[0].round_prizes) == 1


class TestPhaseRestrictions:
    """Tests for actions restricted by game phase."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "phase_test"})
        self.client.get_received()
        self.client.emit("join_game", {"room": "phase_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_spin_during_tossup_phase(self):
        """Spin should be blocked during tossup phase."""
        game = GAMES["phase_test"]
        game.phase = "tossup"

        self.client.emit("spin", {"room": "phase_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("normal" in str(t["args"]).lower() for t in toast_events)

    def test_spin_during_final_phase(self):
        """Spin should be blocked during final phase."""
        game = GAMES["phase_test"]
        game.phase = "final"

        self.client.emit("spin", {"room": "phase_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("normal" in str(t["args"]).lower() for t in toast_events)

    def test_guess_during_tossup_phase(self):
        """Guess should be blocked during tossup phase."""
        game = GAMES["phase_test"]
        game.phase = "tossup"

        self.client.emit("guess", {"room": "phase_test", "letter": "T"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("normal" in str(t["args"]).lower() for t in toast_events)

    def test_guess_during_final_phase(self):
        """Guess should be blocked during final phase."""
        game = GAMES["phase_test"]
        game.phase = "final"

        self.client.emit("guess", {"room": "phase_test", "letter": "T"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("normal" in str(t["args"]).lower() for t in toast_events)


class TestInputValidation:
    """Tests for input validation edge cases."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "validation_test"})
        self.client.get_received()
        self.client.emit("join_game", {"room": "validation_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_guess_invalid_letter(self):
        """Guessing non-letter character should be rejected."""
        game = GAMES["validation_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500

        self.client.emit("guess", {"room": "validation_test", "letter": "1"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("enter a letter" in str(t["args"]).lower() for t in toast_events)

    def test_guess_empty_letter(self):
        """Guessing empty string should be rejected."""
        game = GAMES["validation_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500

        self.client.emit("guess", {"room": "validation_test", "letter": ""})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("enter a letter" in str(t["args"]).lower() for t in toast_events)

    def test_guess_already_used_letter(self):
        """Guessing an already used letter should be rejected."""
        game = GAMES["validation_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500
        game.used_letters.add("L")

        self.client.emit("guess", {"room": "validation_test", "letter": "L"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("already used" in str(t["args"]).lower() for t in toast_events)

    def test_solve_empty_attempt(self):
        """Solving with empty string should be rejected."""
        game = GAMES["validation_test"]
        game.set_puzzle(1, "Test", "HELLO")

        self.client.emit("solve", {"room": "validation_test", "attempt": ""})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("type" in str(t["args"]).lower() for t in toast_events)

    def test_join_game_without_login(self):
        """Joining game without login should be rejected."""
        # Create new client without authentication
        flask_client2 = app.test_client()
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "validation_test"})
        client2.get_received()

        client2.emit("join_game", {"room": "validation_test"})
        received = client2.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("logged in" in str(t["args"]).lower() for t in toast_events)

        client2.disconnect()


class TestConsonantMiss:
    """Tests for consonant miss scenarios."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "miss_test"})
        self.client.get_received()
        self.client.emit("join_game", {"room": "miss_test"})
        self.client.get_received()
        # Add second player for turn advancement tests
        self.flask_client2 = app.test_client()
        create_test_user_session(self.flask_client2, "Player2")
        self.client2 = socketio.test_client(app, flask_test_client=self.flask_client2)
        self.client2.emit("join", {"room": "miss_test"})
        self.client2.get_received()
        self.client2.emit("join_game", {"room": "miss_test"})
        self.client2.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()
        if self.client2.is_connected():
            self.client2.disconnect()

    def test_miss_consonant_with_cash_wedge(self):
        """Missing a consonant with cash wedge should advance turn."""
        game = GAMES["miss_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500

        initial_idx = game.active_idx
        self.client.emit("guess", {"room": "miss_test", "letter": "Z"})
        received = self.client.get_received()

        assert game.active_idx != initial_idx  # Turn advances
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("no z" in str(t["args"]).lower() for t in toast_events)

    def test_hit_consonant_adds_to_bank(self):
        """Hitting consonant with cash wedge should add to round bank."""
        game = GAMES["miss_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500
        game.players[0].round_bank = 0

        self.client.emit("guess", {"room": "miss_test", "letter": "L"})
        self.client.get_received()

        # L appears 2 times in HELLO, so 500 * 2 = 1000
        assert game.players[0].round_bank == 1000


class TestTossupPhase:
    """Tests for tossup phase handlers."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "Player1")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "tossup_test"})
        self.client.get_received()
        # Claim host
        self.client.emit("claim_host", {"room": "tossup_test", "code": "testcode"})
        self.client.get_received()
        # Join game
        self.client.emit("join_game", {"room": "tossup_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_start_tossup(self):
        """Test starting a tossup round."""
        self.client.emit("start_tossup", {"room": "tossup_test"})
        received = self.client.get_received()

        game = GAMES["tossup_test"]
        assert game.phase == "tossup"

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("toss-up started" in str(t["args"]).lower() for t in toast_events)

    def test_end_tossup(self):
        """Test ending a tossup round."""
        game = GAMES["tossup_test"]
        game.phase = "tossup"

        self.client.emit("end_tossup", {"room": "tossup_test"})
        self.client.get_received()

        assert game.phase == "normal"

    def test_buzz_during_tossup(self):
        """Test buzzing in during tossup."""
        game = GAMES["tossup_test"]
        game.phase = "tossup"
        game.tossup_controller_sid = None

        self.client.emit("buzz", {"room": "tossup_test"})
        received = self.client.get_received()

        assert game.tossup_controller_sid is not None
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("buzzed in" in str(t["args"]).lower() for t in toast_events)

    def test_buzz_not_in_tossup(self):
        """Test buzzing not during tossup phase."""
        game = GAMES["tossup_test"]
        game.phase = "normal"

        self.client.emit("buzz", {"room": "tossup_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("toss-up" in str(t["args"]).lower() for t in toast_events)

    def test_buzz_when_locked(self):
        """Test buzzing when player is locked out."""
        game = GAMES["tossup_test"]
        game.phase = "tossup"
        game.tossup_locked_sids.add(game.players[0].claimed_sid)

        self.client.emit("buzz", {"room": "tossup_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("locked out" in str(t["args"]).lower() for t in toast_events)

    def test_buzz_when_someone_already_buzzed(self):
        """Test buzzing when someone else already buzzed."""
        game = GAMES["tossup_test"]
        game.phase = "tossup"
        game.tossup_controller_sid = "other_sid"

        self.client.emit("buzz", {"room": "tossup_test"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("already buzzed" in str(t["args"]).lower() for t in toast_events)

    def test_start_tossup_not_host(self):
        """Test starting tossup without being host."""
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "NotHost")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "tossup_test"})
        client2.get_received()

        client2.emit("start_tossup", {"room": "tossup_test"})
        received = client2.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("host" in str(t["args"]).lower() for t in toast_events)
        client2.disconnect()


class TestFinalPhase:
    """Tests for final phase handlers."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "FinalPlayer")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "final_test"})
        self.client.get_received()
        self.client.emit("claim_host", {"room": "final_test", "code": "testcode"})
        self.client.get_received()
        self.client.emit("join_game", {"room": "final_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_start_final(self):
        """Test starting final round."""
        self.client.emit("start_final", {"room": "final_test"})
        received = self.client.get_received()

        game = GAMES["final_test"]
        assert game.phase == "final"
        assert game.final_stage == "pick"

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("final round" in str(t["args"]).lower() for t in toast_events)

    def test_end_final(self):
        """Test ending final round."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"

        self.client.emit("end_final", {"room": "final_test"})
        self.client.get_received()

        assert game.phase == "normal"
        assert game.final_stage == "off"

    def test_final_pick_consonant(self):
        """Test picking a consonant in final round."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")
        # Add RSTLNE to used letters as they would be in real final
        for ch in "RSTLNE":
            game.used_letters.add(ch)

        self.client.emit("final_pick", {"room": "final_test", "kind": "consonant", "letter": "B"})
        received = self.client.get_received()

        assert "B" in game.final_picks_consonants
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("picked consonant" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_vowel(self):
        """Test picking a vowel in final round."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")
        for ch in "RSTLNE":
            game.used_letters.add(ch)

        self.client.emit("final_pick", {"room": "final_test", "kind": "vowel", "letter": "O"})
        received = self.client.get_received()

        assert game.final_pick_vowel == "O"
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("picked vowel" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_wrong_phase(self):
        """Test picking when not in final pick phase."""
        game = GAMES["final_test"]
        game.phase = "normal"

        self.client.emit("final_pick", {"room": "final_test", "kind": "consonant", "letter": "B"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("not in final pick" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_invalid_kind(self):
        """Test picking with invalid kind."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")

        self.client.emit("final_pick", {"room": "final_test", "kind": "invalid", "letter": "B"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("invalid pick kind" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_vowel_as_consonant(self):
        """Test trying to pick vowel as consonant."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")

        self.client.emit("final_pick", {"room": "final_test", "kind": "consonant", "letter": "A"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("vowel" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_consonant_as_vowel(self):
        """Test trying to pick consonant as vowel."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")

        self.client.emit("final_pick", {"room": "final_test", "kind": "vowel", "letter": "B"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("not a vowel" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_already_picked_consonants(self):
        """Test trying to pick more than 3 consonants."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")
        game.final_picks_consonants = ["B", "C", "D"]

        self.client.emit("final_pick", {"room": "final_test", "kind": "consonant", "letter": "F"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("already picked 3" in str(t["args"]).lower() for t in toast_events)

    def test_final_pick_already_picked_vowel(self):
        """Test trying to pick more than 1 vowel."""
        game = GAMES["final_test"]
        game.phase = "final"
        game.final_stage = "pick"
        game.set_puzzle(1, "Test", "HELLO")
        game.final_pick_vowel = "A"

        self.client.emit("final_pick", {"room": "final_test", "kind": "vowel", "letter": "O"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("already picked a vowel" in str(t["args"]).lower() for t in toast_events)


class TestHostActions:
    """Tests for additional host-only actions."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "HostPlayer")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "host_actions_test"})
        self.client.get_received()
        self.client.emit("claim_host", {"room": "host_actions_test", "code": "testcode"})
        self.client.get_received()
        self.client.emit("join_game", {"room": "host_actions_test"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_set_active_pack(self):
        """Test setting active pack as host."""
        from app import db_get_pack_id

        pack_id = db_get_pack_id("Test Set Pack")

        self.client.emit("set_active_pack", {"room": "host_actions_test", "pack_id": pack_id})
        received = self.client.get_received()

        game = GAMES["host_actions_test"]
        assert game.active_pack_id == pack_id
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("active pack set" in str(t["args"]).lower() for t in toast_events)

    def test_set_active_pack_clear(self):
        """Test clearing active pack."""
        game = GAMES["host_actions_test"]
        game.active_pack_id = 1

        self.client.emit("set_active_pack", {"room": "host_actions_test", "pack_id": None})
        self.client.get_received()

        assert game.active_pack_id is None

    def test_set_active_pack_not_host(self):
        """Test setting active pack without being host."""
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "NotHost")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "host_actions_test"})
        client2.get_received()

        client2.emit("set_active_pack", {"room": "host_actions_test", "pack_id": 1})
        received = client2.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("host" in str(t["args"]).lower() for t in toast_events)
        client2.disconnect()

    def test_set_players(self):
        """Test setting player names."""
        self.client.emit("set_players", {"room": "host_actions_test", "names": ["Alice", "Bob", "Carol"]})
        received = self.client.get_received()

        game = GAMES["host_actions_test"]
        assert len(game.players) == 3
        assert game.players[0].name == "Alice"
        assert game.players[1].name == "Bob"
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("3 players" in str(t["args"]).lower() for t in toast_events)

    def test_set_players_empty(self):
        """Test setting players with empty list."""
        self.client.emit("set_players", {"room": "host_actions_test", "names": []})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("provide" in str(t["args"]).lower() for t in toast_events)

    def test_set_prize_names(self):
        """Test setting prize wedge names."""
        game = GAMES["host_actions_test"]
        # Set up a prize wedge
        game.wheel_slots = [{"type": "PRIZE", "name": "OLD"}, 500, 600]

        self.client.emit("set_prize_names", {"room": "host_actions_test", "names": ["NEW PRIZE"]})
        received = self.client.get_received()

        assert game.wheel_slots[0]["name"] == "NEW PRIZE"
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("updated" in str(t["args"]).lower() for t in toast_events)

    def test_set_config(self):
        """Test setting game config."""
        self.client.emit(
            "set_config",
            {"room": "host_actions_test", "config": {"vowel_cost": 300, "final_seconds": 45, "final_jackpot": 15000}},
        )
        received = self.client.get_received()

        game = GAMES["host_actions_test"]
        assert game.vowel_cost == 300
        assert game.final_seconds == 45
        assert game.final_jackpot == 15000
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("config saved" in str(t["args"]).lower() for t in toast_events)

    def test_set_active_player(self):
        """Test setting active player."""
        game = GAMES["host_actions_test"]
        # Add more players
        game.players = [
            game.players[0]
            if game.players
            else type(
                "Player",
                (),
                {
                    "id": 0,
                    "name": "P1",
                    "claimed_sid": None,
                    "total": 0,
                    "round_bank": 0,
                    "prizes": [],
                    "round_prizes": [],
                    "claimed_user_id": None,
                },
            )(),
        ]
        from app import Player

        game.players.append(Player(1, "Player2"))
        game.players.append(Player(2, "Player3"))

        self.client.emit("set_active_player", {"room": "host_actions_test", "player_idx": 2})
        received = self.client.get_received()

        assert game.active_idx == 2
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("player3" in str(t["args"]).lower() for t in toast_events)

    def test_set_active_player_invalid_index(self):
        """Test setting active player with invalid index."""
        self.client.emit("set_active_player", {"room": "host_actions_test", "player_idx": 99})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("invalid" in str(t["args"]).lower() for t in toast_events)

    def test_release_host_not_host(self):
        """Test releasing host when not the host."""
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "NotHost")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "host_actions_test"})
        client2.get_received()

        client2.emit("release_host", {"room": "host_actions_test"})
        received = client2.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("only the host" in str(t["args"]).lower() for t in toast_events)
        client2.disconnect()


class TestLoadPack:
    """Tests for load_pack handler."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.client = socketio.test_client(app, flask_test_client=app.test_client())
        self.client.emit("join", {"room": "load_pack_test"})
        self.client.get_received()
        self.client.emit("claim_host", {"room": "load_pack_test", "code": "testcode"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_load_pack_no_name(self):
        """Test loading pack without name."""
        self.client.emit("load_pack", {"room": "load_pack_test", "pack_name": "", "text": "Cat|Ans"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("name is required" in str(t["args"]).lower() for t in toast_events)

    def test_load_pack_no_valid_lines(self):
        """Test loading pack with no valid lines."""
        self.client.emit("load_pack", {"room": "load_pack_test", "pack_name": "Test", "text": "no pipe here"})
        received = self.client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("no valid lines" in str(t["args"]).lower() for t in toast_events)


class TestLeaveGameEdgeCases:
    """Tests for leave_game edge cases."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_leave_game_not_in_game(self):
        """Test leaving when not in game."""
        flask_client = app.test_client()
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "leave_edge_test"})
        client.get_received()

        client.emit("leave_game", {"room": "leave_edge_test"})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("not in this game" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()

    def test_leave_game_adjusts_active_idx(self):
        """Test that leaving adjusts active_idx correctly."""
        # Create 3 players
        flask_clients = []
        clients = []
        for i in range(3):
            fc = app.test_client()
            create_test_user_session(fc, f"Player{i}")
            c = socketio.test_client(app, flask_test_client=fc)
            c.emit("join", {"room": "leave_idx_test"})
            c.get_received()
            c.emit("join_game", {"room": "leave_idx_test"})
            c.get_received()
            flask_clients.append(fc)
            clients.append(c)

        game = GAMES["leave_idx_test"]
        game.active_idx = 1  # Second player active

        # First player leaves (player before active leaves)
        clients[0].emit("leave_game", {"room": "leave_idx_test"})
        clients[0].get_received()

        # active_idx should decrease by 1 since a player before active was removed
        assert game.active_idx == 0
        assert len(game.players) == 2

        for c in clients:
            if c.is_connected():
                c.disconnect()

    def test_leave_game_active_player_leaves(self):
        """Test active player leaving adjusts correctly."""
        flask_clients = []
        clients = []
        for i in range(3):
            fc = app.test_client()
            create_test_user_session(fc, f"ActiveLeave{i}")
            c = socketio.test_client(app, flask_test_client=fc)
            c.emit("join", {"room": "active_leave_test"})
            c.get_received()
            c.emit("join_game", {"room": "active_leave_test"})
            c.get_received()
            flask_clients.append(fc)
            clients.append(c)

        game = GAMES["active_leave_test"]
        game.active_idx = 2  # Third player active (last one)

        # Last player leaves
        clients[2].emit("leave_game", {"room": "active_leave_test"})
        clients[2].get_received()

        # active_idx should reset to 0 since removed player was at end
        assert game.active_idx == 0
        assert len(game.players) == 2

        for c in clients:
            if c.is_connected():
                c.disconnect()


class TestJoinGameReconnect:
    """Tests for join_game reconnection scenarios."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_join_game_already_in_game(self):
        """Test joining when already in the game (reconnection)."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "ReconnectPlayer")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "reconnect_test"})
        client.get_received()
        client.emit("join_game", {"room": "reconnect_test"})
        client.get_received()

        game = GAMES["reconnect_test"]
        original_player_count = len(game.players)
        original_sid = game.players[0].claimed_sid

        # Disconnect and reconnect
        client.disconnect()
        client2 = socketio.test_client(app, flask_test_client=flask_client)
        client2.emit("join", {"room": "reconnect_test"})
        client2.get_received()
        client2.emit("join_game", {"room": "reconnect_test"})
        received = client2.get_received()

        # Should have same number of players (reconnected, not added new)
        assert len(game.players) == original_player_count
        # SID should be updated
        assert game.players[0].claimed_sid != original_sid

        you_events = [r for r in received if r["name"] == "you"]
        assert len(you_events) >= 1
        assert you_events[0]["args"][0]["player_idx"] == 0

        client2.disconnect()


class TestBuzzNotPlayer:
    """Test buzzing when not a player."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_buzz_not_claimed_player(self):
        """Test buzzing without claiming a player slot."""
        flask_client = app.test_client()
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "buzz_not_player_test"})
        client.get_received()

        game = GAMES["buzz_not_player_test"]
        game.phase = "tossup"
        game.tossup_controller_sid = None

        client.emit("buzz", {"room": "buzz_not_player_test"})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("claim a player" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()


class TestTossupAllowedPlayers:
    """Test tossup with allowed player restrictions."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_buzz_not_in_allowed_players(self):
        """Test buzzing when not in allowed players list."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "NotAllowed")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "allowed_test"})
        client.get_received()
        client.emit("join_game", {"room": "allowed_test"})
        client.get_received()

        game = GAMES["allowed_test"]
        game.phase = "tossup"
        game.tossup_controller_sid = None
        game.tossup_allowed_player_idxs = [5, 6, 7]  # Not including player 0

        client.emit("buzz", {"room": "allowed_test"})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("not allowed to buzz" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()


class TestClaimPlayer:
    """Test claim_player handler."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_claim_player_no_id(self):
        """Test claiming without player_id fails."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "ClaimTest")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "claim_test"})
        client.get_received()

        client.emit("claim_player", {"room": "claim_test"})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("choose a player slot" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()

    def test_claim_player_invalid_id(self):
        """Test claiming with invalid player_id fails."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "ClaimTest2")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "claim_invalid_test"})
        client.get_received()

        client.emit("claim_player", {"room": "claim_invalid_test", "player_id": 99})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("bad player slot" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()

    def test_claim_player_already_claimed_by_other(self):
        """Test claiming slot claimed by another user fails."""
        from app import Player

        flask_client = app.test_client()
        create_test_user_session(flask_client, "ClaimTest3")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "claim_other_test"})
        client.get_received()

        game = GAMES["claim_other_test"]
        # Add a player claimed by another user
        player = Player(0, "OtherUser")
        player.claimed_user_id = 99999  # Different user
        player.claimed_sid = "other_sid"
        game.players = [player]

        client.emit("claim_player", {"room": "claim_other_test", "player_id": 0})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("claimed by another user" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()

    def test_claim_player_success(self):
        """Test successful player claim."""
        from app import Player

        flask_client = app.test_client()
        create_test_user_session(flask_client, "ClaimSuccess")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "claim_success_test"})
        client.get_received()

        game = GAMES["claim_success_test"]
        game.players = [Player(0, "Unclaimed"), Player(1, "AlsoUnclaimed")]

        client.emit("claim_player", {"room": "claim_success_test", "player_id": 1, "name": "NewName"})
        received = client.get_received()

        assert game.players[1].claimed_sid is not None
        assert game.players[1].name == "NewName"
        you_events = [r for r in received if r["name"] == "you"]
        assert len(you_events) >= 1
        client.disconnect()


class TestReleasePlayer:
    """Test release_player handler."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_release_player_success(self):
        """Test successful player release."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "ReleaseTest")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "release_test"})
        client.get_received()
        client.emit("join_game", {"room": "release_test"})
        client.get_received()

        game = GAMES["release_test"]
        assert len(game.players) == 1
        assert game.players[0].claimed_sid is not None

        client.emit("release_player", {"room": "release_test"})
        received = client.get_received()

        assert game.players[0].claimed_sid is None
        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("released" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()


class TestNewPuzzleEdgeCases:
    """Test new_puzzle edge cases."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_new_puzzle_no_puzzles_left(self):
        """Test new_puzzle when no unused puzzles available."""
        flask_client = app.test_client()
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "no_puzzles_test"})
        client.get_received()
        client.emit("claim_host", {"room": "no_puzzles_test", "code": "testcode"})
        client.get_received()

        game = GAMES["no_puzzles_test"]
        # Mark all puzzles as used (create a huge set of used puzzle IDs)
        game.active_pack_id = 999999  # Non-existent pack

        client.emit("new_puzzle", {"room": "no_puzzles_test"})
        received = client.get_received()

        # Should get message about no puzzles
        toast_events = [r for r in received if r["name"] == "toast"]
        assert len(toast_events) >= 1
        client.disconnect()


class TestGuessEdgeCases:
    """Test additional guess edge cases."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_guess_not_a_letter(self):
        """Test guessing a non-letter character."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "GuessEdge")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "guess_edge_test"})
        client.get_received()
        client.emit("join_game", {"room": "guess_edge_test"})
        client.get_received()

        game = GAMES["guess_edge_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.current_wedge = 500

        client.emit("guess", {"room": "guess_edge_test", "letter": "5"})
        received = client.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("enter a letter" in str(t["args"]).lower() for t in toast_events)
        client.disconnect()


class TestSolveInTossup:
    """Test solve during tossup phase."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_solve_during_tossup_not_controller(self):
        """Test solving during tossup when not the controller."""
        flask_client = app.test_client()
        create_test_user_session(flask_client, "TossupNotCtrl")
        client = socketio.test_client(app, flask_test_client=flask_client)
        client.emit("join", {"room": "tossup_notctrl_test"})
        client.get_received()
        client.emit("join_game", {"room": "tossup_notctrl_test"})
        client.get_received()

        game = GAMES["tossup_notctrl_test"]
        game.phase = "tossup"
        game.set_puzzle(1, "Test", "HELLO")
        game.tossup_controller_sid = "some_other_sid"  # Not this player

        client.emit("solve", {"room": "tossup_notctrl_test", "attempt": "HELLO"})
        received = client.get_received()

        # Should get error message
        toast_events = [r for r in received if r["name"] == "toast"]
        assert len(toast_events) >= 1
        client.disconnect()


class TestRevealAll:
    """Tests for reveal_all handler (TV display feature)."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True
        self.flask_client = app.test_client()
        create_test_user_session(self.flask_client, "RevealHost")
        self.client = socketio.test_client(app, flask_test_client=self.flask_client)
        self.client.emit("join", {"room": "reveal_test"})
        self.client.get_received()
        self.client.emit("claim_host", {"room": "reveal_test", "code": "testcode"})
        self.client.get_received()

    def teardown_method(self):
        if self.client.is_connected():
            self.client.disconnect()

    def test_reveal_all_as_host(self):
        """Test revealing all letters as host."""
        game = GAMES["reveal_test"]
        game.set_puzzle(1, "Test", "HELLO WORLD")
        game.revealed = set()

        self.client.emit("reveal_all", {"room": "reveal_test"})
        received = self.client.get_received()

        # All letters should be revealed
        assert "H" in game.revealed
        assert "E" in game.revealed
        assert "L" in game.revealed
        assert "O" in game.revealed
        assert "W" in game.revealed
        assert "R" in game.revealed
        assert "D" in game.revealed

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("revealed" in str(t["args"]).lower() for t in toast_events)

    def test_reveal_all_not_host(self):
        """Test reveal_all without being host."""
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "NotHost")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "reveal_test"})
        client2.get_received()

        game = GAMES["reveal_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.revealed = set()

        client2.emit("reveal_all", {"room": "reveal_test"})
        received = client2.get_received()

        # Should not reveal letters
        assert len(game.revealed) == 0

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("host" in str(t["args"]).lower() for t in toast_events)
        client2.disconnect()


class TestSpinAsHost:
    """Tests for host spinning on behalf of active player (TV display feature)."""

    def setup_method(self):
        GAMES.clear()
        app.config["TESTING"] = True

    def test_spin_as_host_for_player(self):
        """Test host can spin on behalf of active player."""
        # Create a player
        flask_client1 = app.test_client()
        create_test_user_session(flask_client1, "Player1")
        client1 = socketio.test_client(app, flask_test_client=flask_client1)
        client1.emit("join", {"room": "spin_host_test"})
        client1.get_received()
        client1.emit("join_game", {"room": "spin_host_test"})
        client1.get_received()

        # Create host (different client)
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "HostUser")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "spin_host_test"})
        client2.get_received()
        client2.emit("claim_host", {"room": "spin_host_test", "code": "testcode"})
        client2.get_received()

        game = GAMES["spin_host_test"]
        game.set_puzzle(1, "Test", "HELLO")

        # Host spins (not the active player)
        client2.emit("spin", {"room": "spin_host_test"})
        received = client2.get_received()

        # Spin should work for host - last_spin_index should change
        # Note: wheel_index may be None if spin landed on BANKRUPT/LOSE A TURN
        assert game.last_spin_index is not None
        # Check that state was broadcast
        state_events = [r for r in received if r["name"] == "state"]
        assert len(state_events) >= 1

        client1.disconnect()
        client2.disconnect()

    def test_spin_as_non_host_non_active(self):
        """Test non-host, non-active player cannot spin."""
        # Create first player (active)
        flask_client1 = app.test_client()
        create_test_user_session(flask_client1, "ActivePlayer")
        client1 = socketio.test_client(app, flask_test_client=flask_client1)
        client1.emit("join", {"room": "spin_nonhost_test"})
        client1.get_received()
        client1.emit("join_game", {"room": "spin_nonhost_test"})
        client1.get_received()

        # Create second player (not active, not host)
        flask_client2 = app.test_client()
        create_test_user_session(flask_client2, "OtherPlayer")
        client2 = socketio.test_client(app, flask_test_client=flask_client2)
        client2.emit("join", {"room": "spin_nonhost_test"})
        client2.get_received()
        client2.emit("join_game", {"room": "spin_nonhost_test"})
        client2.get_received()

        game = GAMES["spin_nonhost_test"]
        game.set_puzzle(1, "Test", "HELLO")
        game.active_idx = 0  # First player is active

        # Second player tries to spin (should fail)
        client2.emit("spin", {"room": "spin_nonhost_test"})
        received = client2.get_received()

        toast_events = [r for r in received if r["name"] == "toast"]
        assert any("active player" in str(t["args"]).lower() for t in toast_events)

        client1.disconnect()
        client2.disconnect()
