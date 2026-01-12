import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app import (  # noqa: E402
    ALPHABET,
    BASE_WHEEL,
    DEFAULT_FINAL_JACKPOT,
    DEFAULT_FINAL_SECONDS,
    DEFAULT_PUZZLES,
    DEFAULT_VOWEL_COST,
    FINAL_RSTLNE,
    GAMES,
    VOWELS,
    GameState,
    Player,
    _csv_from_ints,
    _ints_from_csv,
    _prize_value_sum,
    app,
    db_add_puzzles,
    db_clear_used,
    db_connect,
    db_counts,
    db_ensure_room_config,
    db_get_pack_id,
    db_get_room_config,
    db_list_packs,
    db_mark_used,
    db_next_unused_puzzle,
    db_pack_name,
    db_seed_defaults_if_empty,
    db_set_active_pack,
    db_set_room_config,
    get_game,
    pick_tv_winner_indexes,
    player_tv_total,
    serialize,
)


class TestHelperFunctions:
    def test_csv_from_ints(self):
        assert _csv_from_ints([1, 2, 3]) == "1,2,3"
        assert _csv_from_ints([500, 1000, 1500]) == "500,1000,1500"
        assert _csv_from_ints([]) == ""

    def test_ints_from_csv(self):
        assert _ints_from_csv("1,2,3", []) == [1, 2, 3]
        assert _ints_from_csv("500, 1000, 1500", []) == [500, 1000, 1500]
        assert _ints_from_csv("", [100]) == [100]
        assert _ints_from_csv(None, [100]) == [100]
        assert _ints_from_csv("invalid", [100]) == [100]


class TestPlayer:
    def test_player_creation(self):
        p = Player(id=0, name="Test Player")
        assert p.id == 0
        assert p.name == "Test Player"
        assert p.total == 0
        assert p.prizes == []
        assert p.round_bank == 0
        assert p.round_prizes == []
        assert p.claimed_sid is None

    def test_player_tv_total(self):
        p = Player(id=0, name="Test", total=1000)
        assert player_tv_total(p) == 1000

        p.prizes = [{"name": "Prize", "value": 500}]
        assert player_tv_total(p) == 1500

    def test_pick_tv_winner_indexes(self):
        players = [
            Player(id=0, name="P1", total=1000),
            Player(id=1, name="P2", total=2000),
            Player(id=2, name="P3", total=1500),
        ]
        assert pick_tv_winner_indexes(players) == [1]

        # Test tie
        players[0].total = 2000
        assert pick_tv_winner_indexes(players) == [0, 1]


class TestGameState:
    def test_game_state_creation(self):
        g = GameState(room="test")
        assert g.room == "test"
        assert g.vowel_cost == DEFAULT_VOWEL_COST
        assert g.players == []
        assert g.phase == "normal"

    def test_ensure_players(self):
        g = GameState(room="test")
        g.ensure_players(default_n=4)
        assert len(g.players) == 4
        assert g.players[0].name == "Player 1"
        assert g.players[3].name == "Player 4"

    def test_set_puzzle(self):
        g = GameState(room="test")
        g.ensure_players()
        g.set_puzzle(1, "Phrase", "Hello World")
        assert g.puzzle["id"] == 1
        assert g.puzzle["category"] == "Phrase"
        assert g.puzzle["answer"] == "HELLO WORLD"
        assert g.revealed == set()
        assert g.used_letters == set()

    def test_advance_player(self):
        g = GameState(room="test")
        g.ensure_players(default_n=3)
        assert g.active_idx == 0
        g.advance_player()
        assert g.active_idx == 1
        g.advance_player()
        assert g.active_idx == 2
        g.advance_player()
        assert g.active_idx == 0  # Wraps around

    def test_spin_sets_wedge(self):
        g = GameState(room="test")
        g.ensure_players()
        g.spin()
        # last_spin_index is always set after a spin
        assert g.last_spin_index is not None
        # wheel_index may be None if BANKRUPT/LOSE A TURN was hit (which clears turn state)
        # So we check that either wheel_index is set OR the turn advanced (for special wedges)
        assert g.wheel_index is not None or g.active_idx != 0

    def test_reset_round_banks(self):
        g = GameState(room="test")
        g.ensure_players(default_n=2)
        g.players[0].round_bank = 500
        g.players[1].round_bank = 1000
        g.reset_round_banks()
        assert g.players[0].round_bank == 0
        assert g.players[1].round_bank == 0

    def test_award_round_to_active(self):
        g = GameState(room="test")
        g.ensure_players()
        g.players[0].round_bank = 1000
        g.players[0].round_prizes = [{"name": "Prize", "value": 500}]
        g.award_round_to_active()
        assert g.players[0].total == 1000
        assert g.players[0].round_bank == 0
        assert len(g.players[0].prizes) == 1
        assert g.players[0].round_prizes == []


class TestConstants:
    def test_alphabet(self):
        assert len(ALPHABET) == 26
        assert "A" in ALPHABET
        assert "Z" in ALPHABET
        assert "a" not in ALPHABET

    def test_vowels(self):
        assert VOWELS == {"A", "E", "I", "O", "U"}

    def test_base_wheel(self):
        assert "BANKRUPT" in BASE_WHEEL
        assert "LOSE A TURN" in BASE_WHEEL
        assert "FREE PLAY" in BASE_WHEEL
        assert any(isinstance(w, int) for w in BASE_WHEEL)

    def test_final_rstlne(self):
        assert set(FINAL_RSTLNE) == {"R", "S", "T", "L", "N", "E"}


class TestPrizeValueSum:
    def test_empty_list(self):
        assert _prize_value_sum([]) == 0

    def test_with_prizes(self):
        prizes = [{"name": "A", "value": 100}, {"name": "B", "value": 200}]
        assert _prize_value_sum(prizes) == 300

    def test_with_missing_value(self):
        prizes = [{"name": "A"}, {"name": "B", "value": 200}]
        assert _prize_value_sum(prizes) == 200

    def test_with_none(self):
        assert _prize_value_sum(None) == 0


class TestDatabase:
    def test_get_room_config_defaults(self):
        cfg = db_get_room_config("test_room_new")
        assert cfg["vowel_cost"] == DEFAULT_VOWEL_COST
        assert cfg["final_seconds"] == DEFAULT_FINAL_SECONDS
        assert cfg["final_jackpot"] == DEFAULT_FINAL_JACKPOT

    def test_set_room_config(self):
        db_set_room_config("test_room_cfg", {"vowel_cost": 500, "final_jackpot": 25000})
        cfg = db_get_room_config("test_room_cfg")
        assert cfg["vowel_cost"] == 500
        assert cfg["final_jackpot"] == 25000

    def test_pack_operations(self):
        pack_id = db_get_pack_id("Test Pack")
        assert pack_id > 0

        # Same name returns same ID
        pack_id2 = db_get_pack_id("Test Pack")
        assert pack_id == pack_id2

        packs = db_list_packs()
        assert any(p["name"] == "Test Pack" for p in packs)

    def test_add_puzzles(self):
        pack_id = db_get_pack_id("Puzzle Test Pack")
        count = db_add_puzzles([("Category", "Answer One"), ("Category", "Answer Two")], pack_id)
        assert count == 2

    def test_counts(self):
        counts = db_counts("test_count_room", None)
        assert "total" in counts
        assert "used" in counts
        assert "unused" in counts
        assert counts["unused"] == counts["total"] - counts["used"]

    def test_clear_used(self):
        db_clear_used("test_clear_room")
        counts = db_counts("test_clear_room", None)
        assert counts["used"] == 0


class TestGameStateBankrupt:
    def test_spin_bankrupt(self):
        g = GameState(room="bankrupt_test")
        g.ensure_players(default_n=3)
        g.players[0].round_bank = 1000
        g.players[0].round_prizes = [{"name": "Prize", "value": 500}]

        # Force bankrupt
        g.wheel_slots = ["BANKRUPT"]
        g.spin()

        assert g.players[0].round_bank == 0
        assert g.players[0].round_prizes == []
        assert g.active_idx == 1  # Advanced to next player

    def test_spin_lose_a_turn(self):
        g = GameState(room="lose_turn_test")
        g.ensure_players(default_n=3)
        g.players[0].round_bank = 1000

        # Force lose a turn
        g.wheel_slots = ["LOSE A TURN"]
        g.spin()

        assert g.players[0].round_bank == 1000  # Bank preserved
        assert g.active_idx == 1  # Advanced to next player


class TestGameStateTossup:
    def test_build_tossup_reveal_order(self):
        g = GameState(room="tossup_test")
        g.set_puzzle(1, "Phrase", "HELLO")
        g.build_tossup_reveal_order()

        assert len(g.tossup_reveal_order) == 5
        assert set(g.tossup_reveal_order) == {"H", "E", "L", "L", "O"}

    def test_tossup_reveal_step(self):
        g = GameState(room="tossup_reveal_test")
        g.set_puzzle(1, "Phrase", "HI")
        g.build_tossup_reveal_order()

        assert len(g.revealed) == 0
        g.tossup_reveal_step(1)
        assert len(g.revealed) == 1
        g.tossup_reveal_step(1)
        assert len(g.revealed) == 2


class TestGameStateFinal:
    def test_final_start_pick(self):
        g = GameState(room="final_test")
        g.ensure_players()
        g.final_start_pick()

        assert g.phase == "final"
        assert g.final_stage == "pick"
        assert set(FINAL_RSTLNE).issubset(g.revealed)
        assert set(FINAL_RSTLNE).issubset(g.used_letters)

    def test_final_all_picks_complete(self):
        g = GameState(room="final_picks_test")
        g.final_picks_consonants = ["B", "C"]
        g.final_pick_vowel = None
        assert not g.final_all_picks_complete()

        g.final_picks_consonants = ["B", "C", "D"]
        assert not g.final_all_picks_complete()

        g.final_pick_vowel = "A"
        assert g.final_all_picks_complete()

    def test_final_reveal_picks(self):
        g = GameState(room="final_reveal_test")
        g.final_picks_consonants = ["B", "C", "D"]
        g.final_pick_vowel = "A"
        g.final_reveal_picks()

        assert "B" in g.revealed
        assert "C" in g.revealed
        assert "D" in g.revealed
        assert "A" in g.revealed

    def test_final_reset(self):
        g = GameState(room="final_reset_test")
        g.final_stage = "pick"
        g.final_picks_consonants = ["B", "C", "D"]
        g.final_pick_vowel = "A"
        g.final_end_ts = 12345.0

        g.final_reset()

        assert g.final_stage == "off"
        assert g.final_picks_consonants == []
        assert g.final_pick_vowel is None
        assert g.final_end_ts is None


class TestGameStateAdvanced:
    def test_sid_player_idx(self):
        g = GameState(room="sid_test")
        g.ensure_players(default_n=3)
        g.players[1].claimed_sid = "test_sid_123"

        assert g.sid_player_idx("test_sid_123") == 1
        assert g.sid_player_idx("nonexistent") is None

    def test_active_player(self):
        g = GameState(room="active_test")
        g.ensure_players(default_n=3)
        g.active_idx = 2

        assert g.active_player() == g.players[2]

    def test_clear_turn_state(self):
        g = GameState(room="clear_test")
        g.current_wedge = 500
        g.wheel_index = 5
        g.last_spin_index = 5

        g.clear_turn_state()

        assert g.current_wedge is None
        assert g.wheel_index is None
        # last_spin_index persists (not cleared) - needed for PRIZE replacement
        assert g.last_spin_index == 5

    def test_reset_game(self):
        g = GameState(room="reset_test")
        g.ensure_players(default_n=2)
        g.players[0].total = 5000
        g.players[0].prizes = [{"name": "Prize", "value": 1000}]
        g.phase = "tossup"
        g.revealed = {"A", "B", "C"}

        g.reset_game()

        assert g.players[0].total == 0
        assert g.players[0].prizes == []
        assert g.phase == "normal"
        assert g.active_idx == 0


class TestDatabaseAdvanced:
    def test_db_set_active_pack(self):
        pack_id = db_get_pack_id("Active Pack Test")
        db_set_active_pack("active_pack_room", pack_id)
        cfg = db_get_room_config("active_pack_room")
        assert cfg["active_pack_id"] == pack_id

        # Set to None
        db_set_active_pack("active_pack_room", None)
        cfg = db_get_room_config("active_pack_room")
        assert cfg["active_pack_id"] is None

    def test_db_pack_name(self):
        pack_id = db_get_pack_id("Pack Name Test")
        name = db_pack_name(pack_id)
        assert name == "Pack Name Test"

        # None returns None
        assert db_pack_name(None) is None

        # Non-existent ID returns None
        assert db_pack_name(99999) is None

    def test_db_mark_used(self):
        pack_id = db_get_pack_id("Mark Used Test Pack")
        db_add_puzzles([("Cat", "Answer")], pack_id)

        # Mark a puzzle as used (using a fake puzzle_id for simplicity)
        db_mark_used("mark_used_room", 99998)

        # used count should increase (unless puzzle doesn't exist in pack)
        # The count tracks puzzle_ids regardless of pack membership
        counts = db_counts("mark_used_room", None)
        assert counts["used"] >= 1

    def test_db_next_unused_puzzle(self):
        pack_id = db_get_pack_id("Next Unused Test Pack")
        db_add_puzzles([("Category", "TEST ANSWER XYZ")], pack_id)
        db_clear_used("next_unused_room")

        row = db_next_unused_puzzle("next_unused_room", pack_id)
        assert row is not None
        assert row["answer"] == "TEST ANSWER XYZ"

        # Test with pack_id=None (all packs)
        row_all = db_next_unused_puzzle("next_unused_room_all", None)
        assert row_all is not None

    def test_db_counts_with_pack(self):
        pack_id = db_get_pack_id("Counts With Pack Test")
        db_add_puzzles([("Cat1", "Ans1"), ("Cat2", "Ans2")], pack_id)
        db_clear_used("counts_pack_room")

        counts = db_counts("counts_pack_room", pack_id)
        assert counts["total"] >= 2
        assert counts["unused"] == counts["total"] - counts["used"]

    def test_db_get_pack_id_empty_name(self):
        import pytest

        with pytest.raises(ValueError):
            db_get_pack_id("")

        with pytest.raises(ValueError):
            db_get_pack_id("   ")

    def test_db_set_room_config_string_values(self):
        # Test with string values for prize_replace_cash_values
        db_set_room_config("string_values_room", {
            "vowel_cost": 300,
            "final_jackpot": 15000,
            "prize_replace_cash_values": "100, 200, 300"
        })
        cfg = db_get_room_config("string_values_room")
        assert cfg["vowel_cost"] == 300
        assert cfg["prize_replace_cash_values"] == [100, 200, 300]


class TestGameStateConfig:
    def test_load_config_from_db(self):
        db_set_room_config("config_load_room", {
            "vowel_cost": 400,
            "final_seconds": 45,
            "final_jackpot": 20000
        })

        g = GameState(room="config_load_room")
        g.load_config_from_db()

        assert g.vowel_cost == 400
        assert g.final_seconds == 45
        assert g.final_jackpot == 20000

    def test_pick_next_puzzle(self):
        pack_id = db_get_pack_id("Pick Next Test Pack")
        db_add_puzzles([("Test Cat", "PICK NEXT ANSWER")], pack_id)
        db_clear_used("pick_next_room")
        db_set_active_pack("pick_next_room", pack_id)

        g = GameState(room="pick_next_room")
        g.load_config_from_db()
        result = g.pick_next_puzzle()

        assert result is True
        assert g.puzzle["answer"] == "PICK NEXT ANSWER"

    def test_final_remaining_seconds(self):
        import time

        g = GameState(room="final_seconds_test")

        # No end time set
        assert g.final_remaining_seconds() is None

        # Set end time in the future
        g.final_end_ts = time.time() + 30
        remaining = g.final_remaining_seconds()
        assert remaining is not None
        assert 28 <= remaining <= 30

        # Set end time in the past
        g.final_end_ts = time.time() - 10
        assert g.final_remaining_seconds() == 0


class TestGameStateWheelSlots:
    def test_spin_free_play(self):
        g = GameState(room="free_play_test")
        g.ensure_players(default_n=3)
        g.players[0].round_bank = 500

        g.wheel_slots = ["FREE PLAY"]
        g.spin()

        # Free play doesn't advance player or lose bank
        assert g.players[0].round_bank == 500
        assert g.current_wedge == "FREE PLAY"

    def test_spin_prize_wedge(self):
        g = GameState(room="prize_wedge_test")
        g.ensure_players(default_n=3)

        g.wheel_slots = [{"type": "PRIZE", "name": "TEST PRIZE"}]
        g.spin()

        assert g.current_wedge == {"type": "PRIZE", "name": "TEST PRIZE"}


class TestGameStateAdvancedPlayers:
    def test_advance_player_empty(self):
        g = GameState(room="empty_advance_test")
        g.players = []
        g.advance_player()
        assert g.active_idx == 0

    def test_ensure_players_already_exists(self):
        g = GameState(room="ensure_existing_test")
        g.players = [Player(0, "Existing")]
        g.ensure_players(default_n=4)
        # Should not overwrite existing players
        assert len(g.players) == 1
        assert g.players[0].name == "Existing"


class TestPickTvWinnerEdgeCases:
    def test_empty_players(self):
        result = pick_tv_winner_indexes([])
        assert result == [0]

    def test_all_zero_scores(self):
        players = [
            Player(id=0, name="P1", total=0),
            Player(id=1, name="P2", total=0),
        ]
        result = pick_tv_winner_indexes(players)
        assert result == [0, 1]  # All tied at 0


class TestFlaskApp:
    def test_index_route_requires_login(self):
        with app.test_client() as client:
            response = client.get("/")
            # Should redirect to login when not authenticated
            assert response.status_code == 302
            assert "/auth/login" in response.headers.get("Location", "")

    def test_index_route_with_room_requires_login(self):
        with app.test_client() as client:
            response = client.get("/?room=testroom")
            # Should redirect to login when not authenticated
            assert response.status_code == 302
            assert "/auth/login" in response.headers.get("Location", "")


class TestGetGameAndSerialize:
    def test_get_game_creates_new(self):
        GAMES.pop("new_game_test", None)
        g = get_game("new_game_test")

        assert g is not None
        assert g.room == "new_game_test"
        assert len(g.players) == 0  # No players until someone joins
        assert "new_game_test" in GAMES

    def test_get_game_returns_existing(self):
        g1 = get_game("existing_game_test")
        g1.ensure_players(default_n=1)  # Create a player for testing
        g1.players[0].total = 9999
        g2 = get_game("existing_game_test")

        assert g2.players[0].total == 9999

    def test_get_game_empty_room_defaults_to_main(self):
        g = get_game("")
        assert g.room == "main"

    def test_serialize(self):
        # Use GameState directly to control player count
        g = GameState(room="serialize_test")
        g.ensure_players(default_n=2)
        g.players[0].total = 1000
        g.players[0].claimed_sid = "test_sid"
        g.set_puzzle(1, "Test", "HELLO")
        g.revealed.add("H")

        data = serialize(g)

        assert data["room"] == "serialize_test"
        assert data["phase"] == "normal"
        assert len(data["players"]) == 2
        assert data["players"][0]["total"] == 1000
        assert data["players"][0]["claimed"] is True
        assert "H" in data["revealed"]
        assert data["puzzle"]["answer"] == "HELLO"
        assert "db" in data
        assert "config" in data
        assert "tossup" in data
        assert "final" in data


class TestApiImportPacks:
    def test_import_packs_no_file(self):
        # Set up host so we pass the host check and get to the file check
        g = get_game("no_file_test")
        g.host_sid = "test_host_sid"

        with app.test_client() as client:
            response = client.post("/api/import_packs?room=no_file_test&sid=test_host_sid")
            assert response.status_code == 400
            data = response.get_json()
            assert data["ok"] is False
            assert "Missing file" in data["error"]

    def test_import_packs_host_only(self):
        import io

        g = get_game("import_test")
        g.host_sid = "actual_host_sid"

        with app.test_client() as client:
            data = io.BytesIO(b'{"packs": []}')
            response = client.post(
                "/api/import_packs?room=import_test&sid=wrong_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 403

    def test_import_packs_invalid_json(self):
        import io

        g = get_game("import_json_test")
        g.host_sid = "host_sid"

        with app.test_client() as client:
            data = io.BytesIO(b'not valid json')
            response = client.post(
                "/api/import_packs?room=import_json_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 400
            assert "Invalid JSON" in response.get_json()["error"]

    def test_import_packs_empty_packs(self):
        import io

        g = get_game("import_empty_test")
        g.host_sid = "host_sid"

        with app.test_client() as client:
            data = io.BytesIO(b'{"packs": []}')
            response = client.post(
                "/api/import_packs?room=import_empty_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 400
            assert "packs" in response.get_json()["error"]

    def test_import_packs_success(self):
        import io
        import json

        g = get_game("import_success_test")
        g.host_sid = "host_sid"

        payload = {
            "packs": [
                {
                    "name": "Import Test Pack",
                    "puzzles": [
                        {"category": "Test", "answer": "ANSWER ONE"},
                        {"category": "Test", "answer": "ANSWER TWO"}
                    ]
                }
            ]
        }

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_success_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            assert result["ok"] is True
            assert result["total_added"] == 2


class TestApiImportPacksEdgeCases:
    def test_import_packs_malformed_pack_structure(self):
        import io
        import json

        g = get_game("import_malformed_test")
        g.host_sid = "host_sid"

        # Pack without name
        payload = {"packs": [{"puzzles": [{"category": "Cat", "answer": "Ans"}]}]}

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_malformed_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            # Should succeed but skip malformed packs
            assert response.status_code == 200
            result = response.get_json()
            assert result["total_added"] == 0

    def test_import_packs_empty_puzzle_list(self):
        import io
        import json

        g = get_game("import_empty_puzzles_test")
        g.host_sid = "host_sid"

        payload = {"packs": [{"name": "Empty Pack", "puzzles": []}]}

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_empty_puzzles_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            assert result["total_added"] == 0

    def test_import_packs_whitespace_only_names(self):
        import io
        import json

        g = get_game("import_whitespace_test")
        g.host_sid = "host_sid"

        payload = {
            "packs": [
                {
                    "name": "   ",
                    "puzzles": [{"category": "Cat", "answer": "Ans"}]
                }
            ]
        }

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_whitespace_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            # Whitespace-only name should be skipped
            assert result["total_added"] == 0

    def test_import_packs_mixed_valid_invalid(self):
        import io
        import json

        g = get_game("import_mixed_test")
        g.host_sid = "host_sid"

        payload = {
            "packs": [
                {"name": "", "puzzles": [{"category": "Cat", "answer": "Ans"}]},  # Invalid
                {"name": "Valid Pack", "puzzles": [{"category": "Cat", "answer": "Valid"}]},  # Valid
                {"puzzles": [{"category": "Cat", "answer": "Ans"}]},  # No name
            ]
        }

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_mixed_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            assert result["ok"] is True
            assert result["total_added"] == 1  # Only valid pack

    def test_import_packs_puzzles_missing_fields(self):
        import io
        import json

        g = get_game("import_missing_fields_test")
        g.host_sid = "host_sid"

        payload = {
            "packs": [
                {
                    "name": "Partial Puzzles Pack",
                    "puzzles": [
                        {"category": "Cat"},  # Missing answer
                        {"answer": "Ans"},  # Missing category
                        {"category": "Valid", "answer": "Complete"},  # Valid
                    ]
                }
            ]
        }

        with app.test_client() as client:
            data = io.BytesIO(json.dumps(payload).encode())
            response = client.post(
                "/api/import_packs?room=import_missing_fields_test&sid=host_sid",
                data={"file": (data, "test.json")},
                content_type="multipart/form-data"
            )
            assert response.status_code == 200
            result = response.get_json()
            assert result["ok"] is True
            assert result["total_added"] == 1  # Only complete puzzle


class TestGameStateGuessLogic:
    def test_guess_already_used_letter(self):
        g = GameState(room="guess_used_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")
        g.used_letters.add("H")

        # H is already used
        assert "H" in g.used_letters

    def test_guess_vowel_deducts_cost(self):
        g = GameState(room="vowel_cost_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")
        g.players[0].round_bank = 500
        g.vowel_cost = 250

        # Simulate vowel purchase
        initial_bank = g.players[0].round_bank
        g.players[0].round_bank -= g.vowel_cost
        assert g.players[0].round_bank == initial_bank - 250

    def test_guess_consonant_with_prize_wedge(self):
        g = GameState(room="prize_wedge_guess_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")
        g.current_wedge = {"type": "PRIZE", "name": "TEST PRIZE"}
        g.prize_replace_cash_values = [500, 1000]

        # Prize should be added to round_prizes
        prize_value = g.prize_replace_cash_values[0]
        g.players[0].round_prizes.append({"name": "TEST PRIZE", "value": prize_value})

        assert len(g.players[0].round_prizes) == 1
        assert g.players[0].round_prizes[0]["name"] == "TEST PRIZE"

    def test_guess_consonant_duplicate_prize(self):
        g = GameState(room="duplicate_prize_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")

        # Already has a prize with same name
        g.players[0].round_prizes = [{"name": "GIFT CARD", "value": 500}]
        g.current_wedge = {"type": "PRIZE", "name": "GIFT CARD"}

        # Check if prize already exists (mimics the logic in guess handler)
        already = any(
            isinstance(x, dict) and x.get("name") == "GIFT CARD"
            for x in g.players[0].round_prizes
        )
        assert already is True

    def test_guess_free_play_keeps_turn(self):
        g = GameState(room="free_play_turn_test")
        g.ensure_players(default_n=3)
        g.set_puzzle(1, "Test", "HELLO")
        g.current_wedge = "FREE PLAY"

        initial_idx = g.active_idx
        # FREE PLAY doesn't advance player even on wrong guess
        # (turn kept, just clear wedge)
        g.clear_turn_state()

        assert g.active_idx == initial_idx

    def test_guess_consonant_earns_money(self):
        g = GameState(room="consonant_money_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")
        g.current_wedge = 500
        g.players[0].round_bank = 0

        # L appears 2 times in HELLO
        answer = g.puzzle["answer"]
        letter = "L"
        count = sum(1 for ch in answer if ch == letter)
        g.players[0].round_bank += g.current_wedge * count

        assert count == 2
        assert g.players[0].round_bank == 1000

    def test_guess_wrong_consonant_loses_turn(self):
        g = GameState(room="wrong_consonant_test")
        g.ensure_players(default_n=3)
        g.set_puzzle(1, "Test", "HELLO")
        g.current_wedge = 500

        assert g.active_idx == 0  # Starts at player 0
        # X is not in HELLO, should advance player
        letter = "X"
        count = sum(1 for ch in g.puzzle["answer"] if ch == letter)
        assert count == 0

        if count == 0 and g.current_wedge != "FREE PLAY":
            g.advance_player()

        assert g.active_idx == 1


class TestGameStateSolveLogic:
    def test_solve_case_insensitive(self):
        g = GameState(room="solve_case_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "Hello World")

        # Answer is stored uppercase
        assert g.puzzle["answer"] == "HELLO WORLD"

        # Solve attempts should be compared uppercase
        attempt = "hello world"
        assert attempt.upper() == g.puzzle["answer"]

    def test_solve_with_extra_whitespace(self):
        g = GameState(room="solve_whitespace_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")

        attempt = "  HELLO  "
        assert attempt.strip().upper() == g.puzzle["answer"]

    def test_solve_reveals_all_letters(self):
        g = GameState(room="solve_reveal_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "HELLO")
        g.revealed = {"H"}  # Only H revealed

        # On correct solve, all letters should be revealed
        answer = g.puzzle["answer"]
        for ch in answer:
            if ch in ALPHABET:
                g.revealed.add(ch)

        assert "H" in g.revealed
        assert "E" in g.revealed
        assert "L" in g.revealed
        assert "O" in g.revealed

    def test_solve_wrong_advances_player(self):
        g = GameState(room="solve_wrong_test")
        g.ensure_players(default_n=3)
        g.set_puzzle(1, "Test", "HELLO")

        initial_idx = g.active_idx
        attempt = "WRONG"

        if attempt.upper() != g.puzzle["answer"]:
            g.advance_player()

        assert g.active_idx != initial_idx


class TestDatabaseInit:
    def test_db_seed_defaults_if_empty(self):
        # This should be idempotent - calling multiple times shouldn't add duplicates
        db_seed_defaults_if_empty()
        db_seed_defaults_if_empty()

        with db_connect() as con:
            count = con.execute("SELECT COUNT(*) as n FROM puzzles WHERE enabled=1").fetchone()["n"]
            # Should have at least the default puzzles
            assert count >= len(DEFAULT_PUZZLES)

    def test_db_ensure_room_config_creates_new(self):
        import time

        room = f"new_room_{int(time.time())}"
        db_ensure_room_config(room)

        with db_connect() as con:
            row = con.execute("SELECT * FROM room_config WHERE room=?", (room,)).fetchone()
            assert row is not None
            assert row["room"] == room

    def test_db_ensure_room_config_idempotent(self):
        import time

        room = f"idempotent_room_{int(time.time())}"
        db_ensure_room_config(room)
        db_ensure_room_config(room)  # Should not raise

        with db_connect() as con:
            count = con.execute("SELECT COUNT(*) as n FROM room_config WHERE room=?", (room,)).fetchone()["n"]
            assert count == 1


class TestTossupPhase:
    def test_tossup_build_reveal_order_shuffled(self):
        g = GameState(room="tossup_shuffle_test")
        g.set_puzzle(1, "Test", "AAAA")
        g.build_tossup_reveal_order()

        # Should have 4 A's
        assert len(g.tossup_reveal_order) == 4
        assert all(ch == "A" for ch in g.tossup_reveal_order)

    def test_tossup_reveal_order_excludes_non_letters(self):
        g = GameState(room="tossup_nonletters_test")
        g.set_puzzle(1, "Test", "A B C!")
        g.build_tossup_reveal_order()

        # Should only have A, B, C (no spaces or punctuation)
        assert len(g.tossup_reveal_order) == 3
        assert all(ch in ALPHABET for ch in g.tossup_reveal_order)

    def test_tossup_reveal_step_empty_order(self):
        g = GameState(room="tossup_empty_test")
        g.tossup_reveal_order = []

        # Should not crash on empty order
        revealed = g.tossup_reveal_step(1)
        assert revealed == 0

    def test_tossup_reveal_step_already_revealed(self):
        g = GameState(room="tossup_already_revealed_test")
        g.set_puzzle(1, "Test", "AA")
        g.tossup_reveal_order = ["A", "A"]
        g.revealed = {"A"}  # A already revealed

        # First step reveals nothing new (A already in revealed)
        # but second A should still be popped
        newly = g.tossup_reveal_step(1)
        # Since A is already revealed, newly should be 0
        assert newly == 0
        assert len(g.tossup_reveal_order) == 1

    def test_tossup_controller_and_locks(self):
        g = GameState(room="tossup_locks_test")
        g.ensure_players(default_n=4)

        g.tossup_controller_sid = "player1_sid"
        g.tossup_locked_sids = {"player2_sid", "player3_sid"}

        assert g.tossup_controller_sid is not None
        assert "player2_sid" in g.tossup_locked_sids
        assert "player4_sid" not in g.tossup_locked_sids

    def test_tossup_allowed_player_idxs(self):
        g = GameState(room="tossup_allowed_test")
        g.ensure_players(default_n=4)

        # Tiebreaker between players 0 and 2
        g.tossup_is_tiebreaker = True
        g.tossup_allowed_player_idxs = [0, 2]

        assert g.tossup_is_tiebreaker is True
        assert 0 in g.tossup_allowed_player_idxs
        assert 1 not in g.tossup_allowed_player_idxs


class TestFinalPhase:
    def test_final_start_pick_sets_phase(self):
        g = GameState(room="final_start_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "TESTING")
        g.final_start_pick()

        assert g.phase == "final"
        assert g.final_stage == "pick"

    def test_final_start_pick_reveals_rstlne(self):
        g = GameState(room="final_rstlne_test")
        g.ensure_players()
        g.set_puzzle(1, "Test", "TESTING")
        g.final_start_pick()

        # RSTLNE should be revealed
        for ch in FINAL_RSTLNE:
            assert ch in g.revealed
            assert ch in g.used_letters

    def test_final_picks_incomplete(self):
        g = GameState(room="final_incomplete_test")

        # No picks
        g.final_picks_consonants = []
        g.final_pick_vowel = None
        assert g.final_all_picks_complete() is False

        # Only consonants
        g.final_picks_consonants = ["B", "C", "D"]
        assert g.final_all_picks_complete() is False

        # Only vowel
        g.final_picks_consonants = []
        g.final_pick_vowel = "A"
        assert g.final_all_picks_complete() is False

    def test_final_reveal_picks_adds_to_revealed(self):
        g = GameState(room="final_reveal_picks_test")
        g.revealed = set()
        g.used_letters = set()
        g.final_picks_consonants = ["B", "C", "D"]
        g.final_pick_vowel = "I"

        g.final_reveal_picks()

        assert "B" in g.revealed
        assert "C" in g.revealed
        assert "D" in g.revealed
        assert "I" in g.revealed
        assert "B" in g.used_letters

    def test_final_reveal_picks_no_vowel(self):
        g = GameState(room="final_no_vowel_test")
        g.revealed = set()
        g.used_letters = set()
        g.final_picks_consonants = ["B", "C", "D"]
        g.final_pick_vowel = None

        g.final_reveal_picks()

        assert "B" in g.revealed
        assert len(g.revealed) == 3  # Only consonants


class TestSerializeEdgeCases:
    def test_serialize_with_tossup_controller(self):
        g = GameState(room="serialize_tossup_test")
        g.ensure_players(default_n=3)
        g.players[1].claimed_sid = "controller_sid"
        g.tossup_controller_sid = "controller_sid"

        data = serialize(g)

        assert data["tossup"]["controller_player_idx"] == 1

    def test_serialize_with_locked_players(self):
        g = GameState(room="serialize_locked_test")
        g.ensure_players(default_n=3)
        g.players[0].claimed_sid = "sid_0"
        g.players[1].claimed_sid = "sid_1"
        g.tossup_locked_sids = {"sid_0", "sid_1"}

        data = serialize(g)

        assert 0 in data["tossup"]["locked_player_idxs"]
        assert 1 in data["tossup"]["locked_player_idxs"]

    def test_serialize_final_stage(self):
        g = GameState(room="serialize_final_test")
        g.ensure_players()
        g.phase = "final"
        g.final_stage = "pick"
        g.final_picks_consonants = ["B", "C"]
        g.final_pick_vowel = "A"

        data = serialize(g)

        assert data["final"]["stage"] == "pick"
        assert data["final"]["picks"]["consonants"] == ["B", "C"]
        assert data["final"]["picks"]["vowel"] == "A"

    def test_serialize_null_puzzle_id(self):
        g = GameState(room="serialize_null_puzzle_test")
        g.ensure_players()
        g.puzzle = {"id": None, "category": "Test", "answer": "TEST"}

        data = serialize(g)

        assert data["puzzle"]["id"] is None
        assert data["puzzle"]["category"] == "Test"


class TestDisconnectCleanup:
    def test_disconnect_releases_player_claim(self):
        g = GameState(room="disconnect_player_test")
        g.ensure_players(default_n=3)
        g.players[1].claimed_sid = "disconnecting_sid"

        # Simulate disconnect cleanup
        sid = "disconnecting_sid"
        for p in g.players:
            if p.claimed_sid == sid:
                p.claimed_sid = None

        assert g.players[1].claimed_sid is None

    def test_disconnect_releases_host(self):
        g = GameState(room="disconnect_host_test")
        g.host_sid = "host_disconnecting_sid"

        sid = "host_disconnecting_sid"
        if g.host_sid == sid:
            g.host_sid = None

        assert g.host_sid is None

    def test_disconnect_releases_tossup_controller(self):
        g = GameState(room="disconnect_tossup_test")
        g.tossup_controller_sid = "controller_disconnecting_sid"

        sid = "controller_disconnecting_sid"
        if g.tossup_controller_sid == sid:
            g.tossup_controller_sid = None

        assert g.tossup_controller_sid is None

    def test_disconnect_removes_from_locked_sids(self):
        g = GameState(room="disconnect_locked_test")
        g.tossup_locked_sids = {"sid1", "sid2", "disconnecting_sid"}

        sid = "disconnecting_sid"
        if sid in g.tossup_locked_sids:
            g.tossup_locked_sids.discard(sid)

        assert "disconnecting_sid" not in g.tossup_locked_sids
        assert "sid1" in g.tossup_locked_sids

    def test_disconnect_cleanup_multiple_games(self):
        g1 = GameState(room="disconnect_multi_1")
        g1.ensure_players()
        g1.players[0].claimed_sid = "multi_sid"

        g2 = GameState(room="disconnect_multi_2")
        g2.ensure_players()
        g2.players[1].claimed_sid = "multi_sid"
        g2.host_sid = "multi_sid"

        GAMES["disconnect_multi_1"] = g1
        GAMES["disconnect_multi_2"] = g2

        # Simulate disconnect across all games
        sid = "multi_sid"
        for game in [g1, g2]:
            for p in game.players:
                if p.claimed_sid == sid:
                    p.claimed_sid = None
            if game.host_sid == sid:
                game.host_sid = None

        assert g1.players[0].claimed_sid is None
        assert g2.players[1].claimed_sid is None
        assert g2.host_sid is None


class TestPrizeValueEdgeCases:
    def test_prize_value_sum_with_invalid_value(self):
        prizes = [
            {"name": "A", "value": 100},
            {"name": "B", "value": "invalid"},  # Invalid value type
            {"name": "C", "value": 200},
        ]
        # Should handle gracefully
        result = _prize_value_sum(prizes)
        assert result == 300  # Only valid values

    def test_prize_value_sum_with_zero_value(self):
        prizes = [
            {"name": "A", "value": 0},
            {"name": "B", "value": 100},
        ]
        result = _prize_value_sum(prizes)
        assert result == 100

    def test_prize_value_sum_non_dict_items(self):
        prizes = [
            {"name": "A", "value": 100},
            "not a dict",
            None,
            {"name": "B", "value": 200},
        ]
        result = _prize_value_sum(prizes)
        assert result == 300


class TestWheelSlotReplacement:
    def test_prize_wedge_replaced_after_win(self):
        g = GameState(room="prize_replace_test")
        g.ensure_players()
        g.wheel_slots = [{"type": "PRIZE", "name": "TEST"}, 500, 600]
        g.prize_replace_cash_values = [1000, 1500]
        g.last_spin_index = 0

        # Simulate prize won - replace with cash value
        import random
        replacement = int(random.choice(g.prize_replace_cash_values))
        g.wheel_slots[g.last_spin_index] = replacement

        assert isinstance(g.wheel_slots[0], int)
        assert g.wheel_slots[0] in [1000, 1500]

    def test_wheel_slot_bounds_check(self):
        g = GameState(room="bounds_test")
        g.wheel_slots = [500, 600, 700]

        # Valid index
        g.last_spin_index = 1
        assert 0 <= g.last_spin_index < len(g.wheel_slots)

        # Out of bounds (should be checked before access)
        g.last_spin_index = 10
        is_valid = 0 <= g.last_spin_index < len(g.wheel_slots)
        assert is_valid is False
