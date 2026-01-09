import os
import sys
import tempfile

# Set test database path before importing app
_test_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
os.environ["DB_PATH"] = _test_db.name
_test_db.close()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (  # noqa: E402
    ALPHABET,
    BASE_WHEEL,
    DEFAULT_FINAL_JACKPOT,
    DEFAULT_FINAL_SECONDS,
    DEFAULT_VOWEL_COST,
    FINAL_RSTLNE,
    VOWELS,
    GameState,
    Player,
    _csv_from_ints,
    _ints_from_csv,
    _prize_value_sum,
    db_add_puzzles,
    db_clear_used,
    db_counts,
    db_get_pack_id,
    db_get_room_config,
    db_list_packs,
    db_set_room_config,
    pick_tv_winner_indexes,
    player_tv_total,
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
        assert g.wheel_index is not None
        assert g.last_spin_index is not None

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
        assert g.last_spin_index is None

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
