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
