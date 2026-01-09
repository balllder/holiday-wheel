import os
import sys

# Set test database path before importing app
os.environ["DB_PATH"] = ":memory:"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import (
    ALPHABET,
    DEFAULT_VOWEL_COST,
    VOWELS,
    GameState,
    Player,
    _csv_from_ints,
    _ints_from_csv,
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
