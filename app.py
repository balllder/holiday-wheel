import json
import os
import random
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Dict, List, Optional, Set, Tuple

from flask import Flask, jsonify, render_template, request, session
from flask_socketio import SocketIO, emit, join_room

from auth import auth_bp, get_current_user, login_required
from db_auth import db_get_user_by_id, db_init_auth, db_update_room_activity


# Type helper: Flask-SocketIO adds 'sid' attribute to request at runtime
def _get_sid() -> Optional[str]:
    return getattr(request, "sid", None)


HOST_CODE = os.environ.get("HOST_CODE", "holiday")
DB_PATH = os.environ.get("DB_PATH", "puzzles.db")

DEFAULT_VOWEL_COST = 250
DEFAULT_FINAL_SECONDS = 30
DEFAULT_FINAL_JACKPOT = 10000
DEFAULT_PRIZE_REPLACE_CASH = [500, 1000, 1500, 2000, 2500, 3000, 3500]

TOSSUP_AWARD = 1000
FINAL_RSTLNE = list("RSTLNE")

BASE_WHEEL: List[Any] = [
    500,
    550,
    600,
    650,
    700,
    800,
    900,
    300,
    350,
    400,
    450,
    1000,
    1500,
    2000,
    "FREE PLAY",
    {"type": "PRIZE", "name": "GIFT CARD"},
    {"type": "PRIZE", "name": "HOLIDAY MUG"},
    {"type": "PRIZE", "name": "STOCKING STUFFER"},
    "BANKRUPT",
    "LOSE A TURN",
]

DEFAULT_PUZZLES: List[Tuple[str, str]] = [
    ("Phrase", "JINGLE ALL THE WAY"),
    ("Phrase", "PEACE ON EARTH"),
    ("Thing", "UGLY SWEATER"),
    ("Thing", "GINGERBREAD HOUSE"),
    ("Food & Drink", "HOT COCOA"),
    ("Song", "SILENT NIGHT"),
    ("Event", "NEW YEARS EVE"),
    ("Phrase", "DECK THE HALLS"),
]

ALPHABET = set(chr(c) for c in range(ord("A"), ord("Z") + 1))
VOWELS = set("AEIOU")


def is_special_wedge(slot: Any) -> bool:
    """Check if a wedge is a special (non-cash) wedge."""
    if isinstance(slot, str):
        return slot in ("BANKRUPT", "LOSE A TURN", "FREE PLAY")
    if isinstance(slot, dict) and slot.get("type") == "PRIZE":
        return True
    return False


def shuffle_wheel_with_spacing(slots: List[Any]) -> List[Any]:
    """Shuffle wheel slots ensuring special wedges are evenly distributed."""
    special = [s for s in slots if is_special_wedge(s)]
    cash = [s for s in slots if not is_special_wedge(s)]

    random.shuffle(special)
    random.shuffle(cash)

    total = len(slots)
    n_special = len(special)

    if n_special == 0:
        return cash

    # Calculate spacing between special wedges
    spacing = total // n_special

    result = [None] * total

    # Place special wedges at evenly spaced positions
    for i, wedge in enumerate(special):
        pos = (i * spacing + random.randint(0, max(0, spacing - 2))) % total
        # Find nearest empty slot if position is taken
        while result[pos] is not None:
            pos = (pos + 1) % total
        result[pos] = wedge

    # Fill remaining slots with cash values
    cash_idx = 0
    for i in range(total):
        if result[i] is None:
            result[i] = cash[cash_idx]
            cash_idx += 1

    return result


# ----------------------------
# SQLite helpers
# ----------------------------
def db_connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.row_factory = sqlite3.Row
    return con


def _csv_from_ints(xs: List[int]) -> str:
    return ",".join(str(int(x)) for x in xs)


def _ints_from_csv(s: str, fallback: List[int]) -> List[int]:
    try:
        parts = [p.strip() for p in (s or "").split(",") if p.strip()]
        vals = [int(p) for p in parts]
        return vals if vals else list(fallback)
    except Exception:
        return list(fallback)


def db_init():
    with db_connect() as con:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS packs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS puzzles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            answer TEXT NOT NULL,
            enabled INTEGER NOT NULL DEFAULT 1,
            created_at INTEGER NOT NULL,
            pack_id INTEGER,
            FOREIGN KEY(pack_id) REFERENCES packs(id)
        );

        CREATE TABLE IF NOT EXISTS used_puzzles (
            room TEXT NOT NULL,
            puzzle_id INTEGER NOT NULL,
            used_at INTEGER NOT NULL,
            PRIMARY KEY (room, puzzle_id)
        );

        CREATE TABLE IF NOT EXISTS room_config (
            room TEXT PRIMARY KEY,
            vowel_cost INTEGER NOT NULL,
            final_seconds INTEGER NOT NULL,
            final_jackpot INTEGER NOT NULL,
            prize_replace_cash_csv TEXT NOT NULL,
            updated_at INTEGER NOT NULL,
            active_pack_id INTEGER
        );
        """)
        con.commit()

        # Lightweight migration for older DBs that lack pack_id/active_pack_id
        try:
            con.execute("ALTER TABLE puzzles ADD COLUMN pack_id INTEGER")
            con.commit()
        except Exception:
            pass
        try:
            con.execute("ALTER TABLE room_config ADD COLUMN active_pack_id INTEGER")
            con.commit()
        except Exception:
            pass


def db_seed_defaults_if_empty():
    with db_connect() as con:
        n = int(con.execute("SELECT COUNT(*) AS n FROM puzzles WHERE enabled=1").fetchone()["n"])
        if n > 0:
            return
        now = int(time.time())
        for cat, ans in DEFAULT_PUZZLES:
            con.execute(
                "INSERT INTO puzzles(category, answer, enabled, created_at, pack_id) VALUES(?,?,1,?,NULL)",
                (cat, ans.upper(), now),
            )
        con.commit()


def db_ensure_room_config(room: str):
    now = int(time.time())
    with db_connect() as con:
        row = con.execute("SELECT room FROM room_config WHERE room=?", (room,)).fetchone()
        if row:
            return
        con.execute(
            """
            INSERT INTO room_config(room, vowel_cost, final_seconds, final_jackpot, prize_replace_cash_csv, updated_at, active_pack_id)
            VALUES(?,?,?,?,?,?,NULL)
            """,
            (
                room,
                DEFAULT_VOWEL_COST,
                DEFAULT_FINAL_SECONDS,
                DEFAULT_FINAL_JACKPOT,
                _csv_from_ints(DEFAULT_PRIZE_REPLACE_CASH),
                now,
            ),
        )
        con.commit()


def db_get_room_config(room: str) -> Dict[str, Any]:
    db_ensure_room_config(room)
    with db_connect() as con:
        row = con.execute("SELECT * FROM room_config WHERE room=?", (room,)).fetchone()
        if row is None:
            db_ensure_room_config(room)
            row = con.execute("SELECT * FROM room_config WHERE room=?", (room,)).fetchone()

        if row is None:
            return {
                "vowel_cost": DEFAULT_VOWEL_COST,
                "final_seconds": DEFAULT_FINAL_SECONDS,
                "final_jackpot": DEFAULT_FINAL_JACKPOT,
                "prize_replace_cash_values": list(DEFAULT_PRIZE_REPLACE_CASH),
                "updated_at": int(time.time()),
                "active_pack_id": None,
            }

        return {
            "vowel_cost": int(row["vowel_cost"]),
            "final_seconds": int(row["final_seconds"]),
            "final_jackpot": int(row["final_jackpot"]),
            "prize_replace_cash_values": _ints_from_csv(row["prize_replace_cash_csv"], DEFAULT_PRIZE_REPLACE_CASH),
            "updated_at": int(row["updated_at"]),
            "active_pack_id": row["active_pack_id"],
        }


def db_set_room_config(room: str, cfg: Dict[str, Any]):
    db_ensure_room_config(room)
    now = int(time.time())
    vowel_cost = int(cfg.get("vowel_cost", DEFAULT_VOWEL_COST))
    final_seconds = int(cfg.get("final_seconds", DEFAULT_FINAL_SECONDS))
    final_jackpot = int(cfg.get("final_jackpot", DEFAULT_FINAL_JACKPOT))
    values = cfg.get("prize_replace_cash_values", DEFAULT_PRIZE_REPLACE_CASH)
    if isinstance(values, str):
        values = [int(x.strip()) for x in values.split(",") if x.strip()]
    values = [int(x) for x in values] if values else list(DEFAULT_PRIZE_REPLACE_CASH)

    with db_connect() as con:
        con.execute(
            """
            UPDATE room_config
            SET vowel_cost=?, final_seconds=?, final_jackpot=?, prize_replace_cash_csv=?, updated_at=?
            WHERE room=?
            """,
            (vowel_cost, final_seconds, final_jackpot, _csv_from_ints(values), now, room),
        )
        con.commit()


def db_set_active_pack(room: str, pack_id: Optional[int]):
    db_ensure_room_config(room)
    with db_connect() as con:
        con.execute("UPDATE room_config SET active_pack_id=? WHERE room=?", (pack_id, room))
        con.commit()


def db_get_pack_id(pack_name: str) -> int:
    name = pack_name.strip()
    if not name:
        raise ValueError("pack name empty")
    now = int(time.time())
    with db_connect() as con:
        row = con.execute("SELECT id FROM packs WHERE name=?", (name,)).fetchone()
        if row:
            return int(row["id"])
        con.execute("INSERT INTO packs(name, created_at) VALUES(?,?)", (name, now))
        con.commit()
        row2 = con.execute("SELECT id FROM packs WHERE name=?", (name,)).fetchone()
        return int(row2["id"])


def db_list_packs() -> List[Dict[str, Any]]:
    with db_connect() as con:
        rows = con.execute(
            """
            SELECT p.id, p.name,
                   (SELECT COUNT(*) FROM puzzles pu WHERE pu.pack_id=p.id AND pu.enabled=1) AS puzzle_count
            FROM packs p
            ORDER BY p.name COLLATE NOCASE
            """
        ).fetchall()
        return [{"id": int(r["id"]), "name": r["name"], "puzzle_count": int(r["puzzle_count"])} for r in rows]


def db_pack_name(pack_id: Optional[int]) -> Optional[str]:
    if pack_id is None:
        return None
    with db_connect() as con:
        row = con.execute("SELECT name FROM packs WHERE id=?", (pack_id,)).fetchone()
        return row["name"] if row else None


def db_add_puzzles(lines: List[Tuple[str, str]], pack_id: Optional[int]) -> int:
    now = int(time.time())
    with db_connect() as con:
        for cat, ans in lines:
            con.execute(
                "INSERT INTO puzzles(category, answer, enabled, created_at, pack_id) VALUES(?,?,1,?,?)",
                (cat, ans.upper(), now, pack_id),
            )
        con.commit()
        return len(lines)


def db_clear_used(room: str):
    with db_connect() as con:
        con.execute("DELETE FROM used_puzzles WHERE room=?", (room,))
        con.commit()


def db_mark_used(room: str, puzzle_id: int):
    now = int(time.time())
    with db_connect() as con:
        con.execute(
            "INSERT OR IGNORE INTO used_puzzles(room, puzzle_id, used_at) VALUES(?,?,?)",
            (room, puzzle_id, now),
        )
        con.commit()


def db_next_unused_puzzle(room: str, pack_id: Optional[int]) -> Optional[sqlite3.Row]:
    with db_connect() as con:
        if pack_id is None:
            return con.execute(
                """
                SELECT pu.*
                FROM puzzles pu
                LEFT JOIN used_puzzles u
                  ON u.puzzle_id = pu.id AND u.room = ?
                WHERE pu.enabled = 1 AND u.puzzle_id IS NULL
                ORDER BY RANDOM()
                LIMIT 1
                """,
                (room,),
            ).fetchone()

        return con.execute(
            """
            SELECT pu.*
            FROM puzzles pu
            LEFT JOIN used_puzzles u
              ON u.puzzle_id = pu.id AND u.room = ?
            WHERE pu.enabled = 1 AND pu.pack_id = ? AND u.puzzle_id IS NULL
            ORDER BY RANDOM()
            LIMIT 1
            """,
            (room, pack_id),
        ).fetchone()


def db_counts(room: str, pack_id: Optional[int]) -> Dict[str, int]:
    with db_connect() as con:
        if pack_id is None:
            total = int(con.execute("SELECT COUNT(*) AS n FROM puzzles WHERE enabled=1").fetchone()["n"])
            used = int(con.execute("SELECT COUNT(*) AS n FROM used_puzzles WHERE room=?", (room,)).fetchone()["n"])
            return {"total": total, "used": used, "unused": total - used}

        total = int(
            con.execute("SELECT COUNT(*) AS n FROM puzzles WHERE enabled=1 AND pack_id=?", (pack_id,)).fetchone()["n"]
        )
        used = int(
            con.execute(
                """
            SELECT COUNT(*) AS n
            FROM used_puzzles u
            JOIN puzzles pu ON pu.id=u.puzzle_id
            WHERE u.room=? AND pu.pack_id=?
            """,
                (room, pack_id),
            ).fetchone()["n"]
        )
        return {"total": total, "used": used, "unused": total - used}


# ----------------------------
# Game model
# ----------------------------
@dataclass
class Player:
    id: int
    name: str
    total: int = 0
    prizes: List[Dict[str, Any]] = field(default_factory=list)
    round_bank: int = 0
    round_prizes: List[Dict[str, Any]] = field(default_factory=list)
    claimed_sid: Optional[str] = None
    claimed_user_id: Optional[int] = None


def _prize_value_sum(prizes: List[Any]) -> int:
    s = 0
    for pr in prizes or []:
        if isinstance(pr, dict):
            try:
                s += int(pr.get("value", 0) or 0)
            except Exception:
                pass
    return s


def player_tv_total(p: Player) -> int:
    return int(p.total) + _prize_value_sum(p.prizes)


def pick_tv_winner_indexes(players: List[Player]) -> List[int]:
    if not players:
        return [0]
    scores = [player_tv_total(p) for p in players]
    best = max(scores)
    return [i for i, sc in enumerate(scores) if sc == best]


@dataclass
class GameState:
    room: str

    vowel_cost: int = DEFAULT_VOWEL_COST
    final_seconds: int = DEFAULT_FINAL_SECONDS
    final_jackpot: int = DEFAULT_FINAL_JACKPOT
    prize_replace_cash_values: List[int] = field(default_factory=lambda: list(DEFAULT_PRIZE_REPLACE_CASH))
    config_updated_at: int = 0

    active_pack_id: Optional[int] = None

    players: List[Player] = field(default_factory=list)
    active_idx: int = 0

    puzzle: Dict[str, Any] = field(
        default_factory=lambda: {"id": None, "category": "Phrase", "answer": "JINGLE ALL THE WAY"}
    )
    revealed: Set[str] = field(default_factory=set)
    used_letters: Set[str] = field(default_factory=set)

    wheel_slots: List[Any] = field(default_factory=lambda: list(BASE_WHEEL))
    wheel_index: Optional[int] = None
    last_spin_index: Optional[int] = None
    current_wedge: Optional[Any] = None

    host_sid: Optional[str] = None

    phase: str = "normal"  # normal | tossup | final

    tossup_controller_sid: Optional[str] = None
    tossup_locked_sids: Set[str] = field(default_factory=set)
    tossup_reveal_order: List[str] = field(default_factory=list)
    tossup_reveal_task_running: bool = False
    tossup_allowed_player_idxs: List[int] = field(default_factory=list)
    tossup_is_tiebreaker: bool = False

    final_stage: str = "off"
    final_picks_consonants: List[str] = field(default_factory=list)
    final_pick_vowel: Optional[str] = None
    final_end_ts: Optional[float] = None
    final_timer_task_running: bool = False

    def __post_init__(self):
        """Shuffle wheel slots on game creation with even spacing for special wedges."""
        self.wheel_slots = shuffle_wheel_with_spacing(self.wheel_slots)

    def load_config_from_db(self):
        cfg = db_get_room_config(self.room)
        self.vowel_cost = int(cfg["vowel_cost"])
        self.final_seconds = int(cfg["final_seconds"])
        self.final_jackpot = int(cfg["final_jackpot"])
        self.prize_replace_cash_values = list(cfg["prize_replace_cash_values"])
        self.config_updated_at = int(cfg.get("updated_at", 0))
        self.active_pack_id = cfg.get("active_pack_id", None)

    def ensure_players(self, default_n: int = 8):
        if not self.players:
            self.players = [Player(i, f"Player {i+1}") for i in range(default_n)]
            self.active_idx = 0

    def reset_round_banks(self):
        for p in self.players:
            p.round_bank = 0
            p.round_prizes = []

    def clear_turn_state(self):
        self.current_wedge = None
        self.wheel_index = None
        # Note: last_spin_index is NOT cleared here - it persists to track
        # where the wheel last landed (used for PRIZE wedge replacement)

    def set_puzzle(self, pid: int, category: str, answer: str):
        self.puzzle = {"id": pid, "category": category, "answer": answer.upper()}
        self.revealed = set()
        self.used_letters = set()
        self.reset_round_banks()
        self.clear_turn_state()
        self.last_spin_index = None

    def pick_next_puzzle(self) -> bool:
        row = db_next_unused_puzzle(self.room, self.active_pack_id)
        if row is None:
            return False
        pid = int(row["id"])
        db_mark_used(self.room, pid)
        self.set_puzzle(pid, row["category"], row["answer"])
        return True

    def active_player(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.active_idx]

    def sid_player_idx(self, sid: str) -> Optional[int]:
        for i, p in enumerate(self.players):
            if p.claimed_sid == sid:
                return i
        return None

    def advance_player(self):
        if not self.players:
            self.active_idx = 0
            return
        self.active_idx = (self.active_idx + 1) % len(self.players)
        self.clear_turn_state()

    def spin(self):
        idx = random.randrange(len(self.wheel_slots))
        self.wheel_index = idx
        self.last_spin_index = idx
        self.current_wedge = self.wheel_slots[idx]

        if self.current_wedge == "BANKRUPT":
            p = self.active_player()
            p.round_bank = 0
            p.round_prizes = []
            self.clear_turn_state()
            self.advance_player()

        elif self.current_wedge == "LOSE A TURN":
            self.clear_turn_state()
            self.advance_player()

    def award_round_to_active(self):
        p = self.active_player()
        p.total += p.round_bank
        for pr in p.round_prizes:
            p.prizes.append(pr)
        p.round_bank = 0
        p.round_prizes = []

    def reset_game(self):
        for p in self.players:
            p.total = 0
            p.prizes = []
            p.round_bank = 0
            p.round_prizes = []

        self.active_idx = 0
        self.wheel_slots = shuffle_wheel_with_spacing(list(BASE_WHEEL))
        self.revealed = set()
        self.used_letters = set()
        self.clear_turn_state()
        self.last_spin_index = None

        self.phase = "normal"
        self.tossup_controller_sid = None
        self.tossup_locked_sids = set()
        self.tossup_reveal_order = []
        self.tossup_reveal_task_running = False
        self.tossup_allowed_player_idxs = []
        self.tossup_is_tiebreaker = False

        self.final_stage = "off"
        self.final_picks_consonants = []
        self.final_pick_vowel = None
        self.final_end_ts = None
        self.final_timer_task_running = False

        db_clear_used(self.room)
        self.pick_next_puzzle()

    def build_tossup_reveal_order(self):
        ans = self.puzzle["answer"].upper()
        letters = [ch for ch in ans if ch in ALPHABET]
        random.shuffle(letters)
        self.tossup_reveal_order = letters

    def tossup_reveal_step(self, n: int = 1) -> int:
        newly = 0
        for _ in range(n):
            if not self.tossup_reveal_order:
                break
            ch = self.tossup_reveal_order.pop()
            if ch not in self.revealed:
                self.revealed.add(ch)
                newly += 1
        return newly

    def final_reset(self):
        self.final_stage = "off"
        self.final_picks_consonants = []
        self.final_pick_vowel = None
        self.final_end_ts = None

    def final_start_pick(self):
        self.phase = "final"
        self.final_stage = "pick"
        self.final_picks_consonants = []
        self.final_pick_vowel = None
        self.final_end_ts = None
        self.clear_turn_state()

        self.pick_next_puzzle()
        for ch in FINAL_RSTLNE:
            self.revealed.add(ch)
            self.used_letters.add(ch)

    def final_all_picks_complete(self) -> bool:
        return len(self.final_picks_consonants) >= 3 and (self.final_pick_vowel is not None)

    def final_reveal_picks(self):
        for ch in self.final_picks_consonants:
            self.revealed.add(ch)
            self.used_letters.add(ch)
        if self.final_pick_vowel:
            self.revealed.add(self.final_pick_vowel)
            self.used_letters.add(self.final_pick_vowel)

    def final_remaining_seconds(self) -> Optional[int]:
        if self.final_end_ts is None:
            return None
        rem = int(self.final_end_ts - time.time())
        return max(0, rem)


app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
if os.environ.get("FLASK_ENV") == "production":
    app.config["SESSION_COOKIE_SECURE"] = True

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "").strip()
cors_allowed = "*" if not CORS_ORIGINS else [o.strip() for o in CORS_ORIGINS.split(",") if o.strip()]
ASYNC_MODE = os.environ.get("SOCKETIO_ASYNC_MODE", "gevent")
socketio = SocketIO(app, cors_allowed_origins=cors_allowed, async_mode=ASYNC_MODE)

# Register auth blueprint
app.register_blueprint(auth_bp)

# Initialize databases
db_init()
db_seed_defaults_if_empty()
db_init_auth()

GAMES: Dict[str, GameState] = {}


def get_game(room: str) -> GameState:
    room = room or "main"
    if room not in GAMES:
        g = GameState(room=room)
        # Start with empty players - they join dynamically
        g.load_config_from_db()
        if not g.pick_next_puzzle():
            g.set_puzzle(0, "Phrase", "JINGLE ALL THE WAY")
        GAMES[room] = g
    else:
        GAMES[room].load_config_from_db()
    return GAMES[room]


def serialize(g: GameState) -> dict:
    counts = db_counts(g.room, g.active_pack_id)
    controller_idx = g.sid_player_idx(g.tossup_controller_sid) if g.tossup_controller_sid else None
    remaining = g.final_remaining_seconds()
    packs = db_list_packs()
    active_pack_name = db_pack_name(g.active_pack_id)

    return {
        "room": g.room,
        "phase": g.phase,
        "players": [
            {
                "id": p.id,
                "name": p.name,
                "total": p.total,
                "prizes": p.prizes,
                "prize_value_total": _prize_value_sum(p.prizes),
                "round_bank": p.round_bank,
                "round_prizes": p.round_prizes,
                "round_prize_value_total": _prize_value_sum(p.round_prizes),
                "claimed": p.claimed_sid is not None,
            }
            for p in g.players
        ],
        "active_idx": g.active_idx,
        "puzzle": {"id": g.puzzle.get("id"), "category": g.puzzle["category"], "answer": g.puzzle["answer"]},
        "revealed": sorted(g.revealed),
        "used": sorted(g.used_letters),
        "current_wedge": g.current_wedge,
        "wheel_index": g.wheel_index,
        "wheel_slots": g.wheel_slots,
        "host": {"claimed": g.host_sid is not None},
        "db": counts,
        "packs": packs,
        "active_pack_id": g.active_pack_id,
        "active_pack_name": active_pack_name,
        "config": {
            "vowel_cost": g.vowel_cost,
            "final_seconds": g.final_seconds,
            "final_jackpot": g.final_jackpot,
            "prize_replace_cash_values": g.prize_replace_cash_values,
            "updated_at": g.config_updated_at,
        },
        "tossup": {
            "controller_player_idx": controller_idx,
            "locked_player_idxs": [
                i
                for i, p in enumerate(g.players)
                if p.claimed_sid in g.tossup_locked_sids and p.claimed_sid is not None
            ],
            "allowed_player_idxs": list(g.tossup_allowed_player_idxs),
            "is_tiebreaker": bool(g.tossup_is_tiebreaker),
        },
        "final": {
            "stage": g.final_stage,
            "picks": {"consonants": g.final_picks_consonants, "vowel": g.final_pick_vowel},
            "remaining_seconds": remaining,
            "jackpot": g.final_jackpot,
        },
    }


def broadcast(room: str):
    g = get_game(room)
    socketio.emit("state", serialize(g), room=room)


@app.get("/")
@login_required
def index():
    room = request.args.get("room", "main")
    user = get_current_user()
    return render_template("index.html", room=room, user=user)


@app.get("/tv/<room>")
@login_required
def tv_display(room: str):
    """TV display page optimized for AppleTV and large screens."""
    user = get_current_user()
    return render_template("tv.html", room=room, user=user)


def start_tossup_reveal_loop(room: str):
    g = get_game(room)
    if g.tossup_reveal_task_running:
        return
    g.tossup_reveal_task_running = True

    def loop():
        try:
            while True:
                gg = get_game(room)
                if gg.phase != "tossup":
                    break
                if gg.tossup_controller_sid is not None:
                    break
                if not gg.tossup_reveal_order:
                    break

                changed = gg.tossup_reveal_step(n=1)
                if changed:
                    broadcast(room)
                socketio.sleep(1.2)
        finally:
            get_game(room).tossup_reveal_task_running = False

    socketio.start_background_task(loop)


def start_final_timer_loop(room: str):
    g = get_game(room)
    if g.final_timer_task_running:
        return
    g.final_timer_task_running = True

    def loop():
        try:
            while True:
                gg = get_game(room)
                if gg.phase != "final" or gg.final_stage != "running":
                    break
                rem = gg.final_remaining_seconds()
                broadcast(room)
                if rem is not None and rem <= 0:
                    gg.final_stage = "done"
                    gg.phase = "normal"
                    gg.final_end_ts = None
                    socketio.emit("toast", {"msg": "Final time is up!"}, room=room)
                    broadcast(room)
                    break
                socketio.sleep(1.0)
        finally:
            get_game(room).final_timer_task_running = False

    socketio.start_background_task(loop)


@socketio.on("join")
def on_join(data):
    room = (data or {}).get("room", "main")
    join_room(room)
    g = get_game(room)

    # Get user from session
    user_id = session.get("user_id")
    sid = _get_sid()

    # Update room activity
    db_update_room_activity(room, user_id)

    # Auto-restore player claim for authenticated users
    if user_id:
        for i, p in enumerate(g.players):
            if p.claimed_user_id == user_id and p.claimed_sid is None:
                p.claimed_sid = sid
                emit("you", {"player_idx": i})
                emit("toast", {"msg": f"Restored your claim on {p.name}."})
                broadcast(room)
                break

    emit("state", serialize(g))


@socketio.on("list_packs")
def list_packs(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    emit("packs", {"packs": db_list_packs()})
    emit("state", serialize(g))


@socketio.on("set_active_pack")
def set_active_pack(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    pack_id = (data or {}).get("pack_id", None)
    if pack_id is None:
        db_set_active_pack(room, None)
    else:
        try:
            db_set_active_pack(room, int(pack_id))
        except Exception:
            emit("toast", {"msg": "Bad pack id."})
            return

    g.load_config_from_db()
    emit("toast", {"msg": f"Active pack set to: {db_pack_name(g.active_pack_id) or 'ALL'}"})
    broadcast(room)


@socketio.on("disconnect")
def on_disconnect():
    for g in GAMES.values():
        changed = False
        for p in g.players:
            if p.claimed_sid == _get_sid():
                p.claimed_sid = None
                changed = True
        if g.host_sid == _get_sid():
            g.host_sid = None
            changed = True
        if g.tossup_controller_sid == _get_sid():
            g.tossup_controller_sid = None
            changed = True
        if _get_sid() in g.tossup_locked_sids:
            g.tossup_locked_sids.discard(_get_sid())
            changed = True
        if changed:
            broadcast(g.room)


@socketio.on("claim_host")
def claim_host(data):
    room = (data or {}).get("room", "main")
    code = (data or {}).get("code", "")
    g = get_game(room)

    if code != HOST_CODE:
        emit("toast", {"msg": "Invalid host code."})
        emit("host_granted", {"granted": False})
        return

    g.host_sid = _get_sid()
    emit("host_granted", {"granted": True})
    emit("toast", {"msg": "Host mode enabled on this device."})
    broadcast(room)


@socketio.on("release_host")
def release_host(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if g.host_sid != _get_sid():
        emit("toast", {"msg": "Only the host can release host mode."})
        return
    g.host_sid = None
    emit("host_granted", {"granted": False})
    emit("toast", {"msg": "Host released."})
    broadcast(room)


@socketio.on("claim_player")
def claim_player(data):
    room = (data or {}).get("room", "main")
    player_id = (data or {}).get("player_id", None)
    name = str((data or {}).get("name", "")).strip()
    g = get_game(room)

    user_id = session.get("user_id")
    sid = _get_sid()

    try:
        pid = int(player_id)
    except Exception:
        emit("toast", {"msg": "Choose a player slot to claim."})
        return

    if pid < 0 or pid >= len(g.players):
        emit("toast", {"msg": "Bad player slot."})
        return

    p = g.players[pid]

    # Check if slot is claimed by another user
    if p.claimed_user_id is not None and p.claimed_user_id != user_id:
        emit("toast", {"msg": "That player slot is claimed by another user."})
        return

    # Check if slot is claimed by another session (non-user)
    if p.claimed_sid is not None and p.claimed_sid != sid:
        if p.claimed_user_id is None:  # Only block if not our user
            emit("toast", {"msg": "That player slot is already claimed."})
            return

    # Release any other claims by this user/sid
    for op in g.players:
        if op.claimed_sid == sid:
            op.claimed_sid = None
        if user_id and op.claimed_user_id == user_id:
            op.claimed_user_id = None

    p.claimed_sid = sid
    p.claimed_user_id = user_id

    # Use display_name from session if no name provided
    if not name and user_id:
        name = session.get("display_name", "")
    if name:
        p.name = name[:24]

    emit("you", {"player_idx": pid})
    emit("toast", {"msg": f"You claimed {p.name}."})
    broadcast(room)


@socketio.on("release_player")
def release_player(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    user_id = session.get("user_id")
    sid = _get_sid()
    changed = False
    for p in g.players:
        if p.claimed_sid == sid:
            p.claimed_sid = None
            p.claimed_user_id = None
            changed = True
        elif user_id and p.claimed_user_id == user_id:
            p.claimed_user_id = None
            changed = True
    if changed:
        emit("you", {"player_idx": None})
        emit("toast", {"msg": "Released your player slot."})
        broadcast(room)


@socketio.on("join_game")
def join_game(data):
    """Join the game as a new player (must be logged in)."""
    room = (data or {}).get("room", "main")
    user_id = session.get("user_id")

    if not user_id:
        emit("toast", {"msg": "You must be logged in to join the game."})
        return

    user = db_get_user_by_id(user_id)
    if not user:
        emit("toast", {"msg": "User not found. Please log in again."})
        return

    name = user["display_name"]
    g = get_game(room)
    sid = _get_sid()

    # Check if already in the game (by user_id)
    for i, p in enumerate(g.players):
        if p.claimed_user_id == user_id:
            # Update socket connection
            p.claimed_sid = sid
            p.name = name  # Sync name in case it changed
            join_room(room)
            emit("you", {"player_idx": i})
            broadcast(room)
            return

    # Add new player
    new_id = len(g.players)
    g.players.append(Player(id=new_id, name=name, claimed_sid=sid, claimed_user_id=user_id))
    join_room(room)
    emit("you", {"player_idx": new_id})
    emit("toast", {"msg": f"Joined as {name}!"})
    broadcast(room)


@socketio.on("leave_game")
def leave_game(data):
    """Leave the game and remove yourself from the player list."""
    room = (data or {}).get("room", "main")
    g = get_game(room)
    user_id = session.get("user_id")
    sid = _get_sid()

    # Find and remove the player
    player_idx = None
    for i, p in enumerate(g.players):
        if p.claimed_sid == sid or (user_id and p.claimed_user_id == user_id):
            player_idx = i
            break

    if player_idx is None:
        emit("toast", {"msg": "You're not in this game."})
        return

    player_name = g.players[player_idx].name
    del g.players[player_idx]

    # Update player IDs to be sequential
    for i, p in enumerate(g.players):
        p.id = i

    # Adjust active_idx if needed
    if g.active_idx >= len(g.players):
        g.active_idx = 0 if g.players else 0
    elif player_idx < g.active_idx:
        g.active_idx -= 1

    emit("you", {"player_idx": None})
    emit("toast", {"msg": f"{player_name} left the game."})
    broadcast(room)


def require_active_player(g: GameState) -> bool:
    p = g.active_player()
    return p is not None and p.claimed_sid == _get_sid()


@socketio.on("load_pack")
def load_pack(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    pack_name = str((data or {}).get("pack_name", "")).strip()
    if not pack_name:
        emit("toast", {"msg": "Pack name is required."})
        return

    text = (data or {}).get("text", "")
    lines: List[Tuple[str, str]] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line or "|" not in line:
            continue
        cat, ans = [p.strip() for p in line.split("|", 1)]
        if cat and ans:
            lines.append((cat, ans))

    if not lines:
        emit("toast", {"msg": "No valid lines found."})
        return

    pack_id = db_get_pack_id(pack_name)
    n = db_add_puzzles(lines, pack_id)

    emit("toast", {"msg": f"Saved pack '{pack_name}' with {n} puzzles."})
    broadcast(room)


@socketio.on("new_puzzle")
def new_puzzle(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return
    ok = g.pick_next_puzzle()
    if not ok:
        emit("toast", {"msg": "No unused puzzles left in this pack (or DB). New Game to reuse."})
    else:
        emit("toast", {"msg": f"New puzzle loaded (id: {g.puzzle.get('id')})."})
    broadcast(room)


@socketio.on("new_game")
def new_game(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return
    g.reset_game()
    emit("toast", {"msg": "New game started."})
    broadcast(room)


@socketio.on("set_active_player")
def set_active_player(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return
    player_idx = data.get("player_idx")
    if not isinstance(player_idx, int) or player_idx < 0 or player_idx >= len(g.players):
        emit("toast", {"msg": "Invalid player index."})
        return
    g.active_idx = player_idx
    emit("toast", {"msg": f"Active player set to {g.players[player_idx].name}."})
    broadcast(room)


@socketio.on("spin")
def spin(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)

    if g.phase != "normal":
        emit("toast", {"msg": "Spin is only allowed during normal rounds."})
        return
    if not require_active_player(g):
        emit("toast", {"msg": "Only the active player can spin."})
        return

    g.spin()
    broadcast(room)


@socketio.on("guess")
def guess(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)

    if g.phase != "normal":
        emit("toast", {"msg": "Letter guesses are only allowed during normal rounds."})
        return
    if not require_active_player(g):
        emit("toast", {"msg": "Only the active player can guess."})
        return

    letter = str((data or {}).get("letter", "")).upper().strip()
    if len(letter) != 1 or letter not in ALPHABET:
        emit("toast", {"msg": "Enter a letter A–Z."})
        return

    p = g.active_player()

    if letter in g.used_letters:
        emit("toast", {"msg": f"{letter} already used."})
        return

    if letter in VOWELS:
        if p.round_bank < g.vowel_cost:
            emit("toast", {"msg": f"Need ${g.vowel_cost} to buy a vowel."})
            return
        p.round_bank -= g.vowel_cost

    if letter not in VOWELS and g.current_wedge is None:
        emit("toast", {"msg": "Spin before guessing a consonant."})
        return

    g.used_letters.add(letter)
    answer = g.puzzle["answer"].upper()
    count = sum(1 for ch in answer if ch == letter)
    if count > 0:
        g.revealed.add(letter)

    if count <= 0:
        if isinstance(g.current_wedge, dict) and g.current_wedge.get("type") == "PRIZE":
            emit("toast", {"msg": "Missed! Lost the prize and your turn."})
            g.clear_turn_state()
            g.advance_player()
            broadcast(room)
            return

        if g.current_wedge != "FREE PLAY":
            g.advance_player()

        emit("toast", {"msg": f"No {letter}'s."})
        g.clear_turn_state()
        broadcast(room)
        return

    if letter not in VOWELS:
        w = g.current_wedge

        if isinstance(w, int):
            p.round_bank += w * count
            emit("toast", {"msg": f"{count} {letter}(s). +${w*count}"})
            g.clear_turn_state()
            broadcast(room)
            return

        if isinstance(w, dict) and w.get("type") == "PRIZE":
            prize_name = w.get("name", "PRIZE")
            prize_value = int(random.choice(g.prize_replace_cash_values)) if g.prize_replace_cash_values else 1000

            already = any(isinstance(x, dict) and x.get("name") == prize_name for x in p.round_prizes)
            if not already:
                p.round_prizes.append({"name": prize_name, "value": prize_value})

            if g.last_spin_index is not None and 0 <= g.last_spin_index < len(g.wheel_slots):
                g.wheel_slots[g.last_spin_index] = int(random.choice(g.prize_replace_cash_values))

            emit("toast", {"msg": f"Prize banked: {prize_name} (${prize_value}). Spin again!"})
            g.clear_turn_state()
            broadcast(room)
            return

        if w == "FREE PLAY":
            emit("toast", {"msg": f"{count} {letter}(s). Free Play!"})
            g.clear_turn_state()
            broadcast(room)
            return

        emit("toast", {"msg": f"{count} {letter}(s)."})
        g.clear_turn_state()
        broadcast(room)
        return

    emit("toast", {"msg": f"{count} {letter}(s)."})
    g.clear_turn_state()
    broadcast(room)


@socketio.on("solve")
def solve(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)

    attempt = str((data or {}).get("attempt", "")).strip().upper()
    if not attempt:
        emit("toast", {"msg": "Type a solve attempt."})
        return

    answer = g.puzzle["answer"].strip().upper()
    if attempt != answer:
        emit("toast", {"msg": "Incorrect solve."})
        g.clear_turn_state()
        g.advance_player()
        broadcast(room)
        return

    for ch in answer:
        if ch in ALPHABET:
            g.revealed.add(ch)

    g.award_round_to_active()
    g.clear_turn_state()

    if not g.pick_next_puzzle():
        emit("toast", {"msg": "Solved! No unused puzzles left (in this pack). New Game to reuse."})
    else:
        emit("toast", {"msg": f"Solved! Next puzzle loaded (id: {g.puzzle.get('id')})."})
    broadcast(room)


@socketio.on("buzz")
def buzz(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)

    if g.phase != "tossup":
        emit("toast", {"msg": "Buzz is only available during toss-up."})
        return

    sid = _get_sid()
    if sid in g.tossup_locked_sids:
        emit("toast", {"msg": "You are locked out for this toss-up."})
        return

    if g.tossup_controller_sid is not None:
        emit("toast", {"msg": "Someone else already buzzed in."})
        return

    player_idx = None
    for i, p in enumerate(g.players):
        if p.claimed_sid == sid:
            player_idx = i
            break

    if player_idx is None:
        emit("toast", {"msg": "Claim a player slot first."})
        return

    if g.tossup_allowed_player_idxs and player_idx not in g.tossup_allowed_player_idxs:
        emit("toast", {"msg": "You are not allowed to buzz in this round."})
        return

    g.tossup_controller_sid = sid
    g.active_idx = player_idx
    emit("toast", {"msg": f"{g.players[player_idx].name} buzzed in!"}, room=room)
    broadcast(room)


@socketio.on("start_tossup")
def start_tossup(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    g.phase = "tossup"
    g.tossup_controller_sid = None
    g.tossup_locked_sids = set()
    g.tossup_allowed_player_idxs = []
    g.tossup_is_tiebreaker = False
    g.revealed = set()
    g.used_letters = set()
    g.build_tossup_reveal_order()
    g.clear_turn_state()

    emit("toast", {"msg": "Toss-up started!"})
    broadcast(room)
    start_tossup_reveal_loop(room)


@socketio.on("end_tossup")
def end_tossup(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    g.phase = "normal"
    g.tossup_controller_sid = None
    g.tossup_locked_sids = set()
    g.tossup_reveal_order = []
    g.tossup_allowed_player_idxs = []

    emit("toast", {"msg": "Toss-up ended."})
    broadcast(room)


@socketio.on("start_final")
def start_final(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    g.final_start_pick()
    emit("toast", {"msg": "Final round started! Pick 3 consonants and 1 vowel."})
    broadcast(room)


@socketio.on("end_final")
def end_final(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    g.phase = "normal"
    g.final_reset()
    emit("toast", {"msg": "Final round ended."})
    broadcast(room)


@socketio.on("final_pick")
def final_pick(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)

    if g.phase != "final" or g.final_stage != "pick":
        emit("toast", {"msg": "Not in final pick phase."})
        return

    sid = _get_sid()
    player_idx = None
    for i, p in enumerate(g.players):
        if p.claimed_sid == sid:
            player_idx = i
            break

    if player_idx is None or player_idx != g.active_idx:
        emit("toast", {"msg": "Only the active player can pick."})
        return

    kind = (data or {}).get("kind", "")
    letter = str((data or {}).get("letter", "")).upper().strip()

    if len(letter) != 1 or letter not in ALPHABET:
        emit("toast", {"msg": "Enter a letter A–Z."})
        return

    if letter in g.used_letters:
        emit("toast", {"msg": f"{letter} already picked or in RSTLNE."})
        return

    if kind == "consonant":
        if letter in VOWELS:
            emit("toast", {"msg": f"{letter} is a vowel."})
            return
        if len(g.final_picks_consonants) >= 3:
            emit("toast", {"msg": "Already picked 3 consonants."})
            return
        g.final_picks_consonants.append(letter)
        g.used_letters.add(letter)
        emit("toast", {"msg": f"Picked consonant: {letter}"})
    elif kind == "vowel":
        if letter not in VOWELS:
            emit("toast", {"msg": f"{letter} is not a vowel."})
            return
        if g.final_pick_vowel is not None:
            emit("toast", {"msg": "Already picked a vowel."})
            return
        g.final_pick_vowel = letter
        g.used_letters.add(letter)
        emit("toast", {"msg": f"Picked vowel: {letter}"})
    else:
        emit("toast", {"msg": "Invalid pick kind."})
        return

    if g.final_all_picks_complete():
        g.final_reveal_picks()
        g.final_stage = "running"
        g.final_end_ts = time.time() + g.final_seconds
        emit("toast", {"msg": "All picks complete! Solve now!"}, room=room)
        start_final_timer_loop(room)

    broadcast(room)


@socketio.on("set_players")
def set_players(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    names = (data or {}).get("names", [])
    if not isinstance(names, list) or len(names) == 0:
        emit("toast", {"msg": "Provide a list of player names."})
        return

    g.players = [Player(i, str(n)[:30]) for i, n in enumerate(names)]
    g.active_idx = 0
    emit("toast", {"msg": f"Set {len(g.players)} players."})
    broadcast(room)


@socketio.on("set_prize_names")
def set_prize_names(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    names = (data or {}).get("names", [])
    if not isinstance(names, list):
        emit("toast", {"msg": "Provide a list of prize names."})
        return

    prize_idx = 0
    for i, slot in enumerate(g.wheel_slots):
        if isinstance(slot, dict) and slot.get("type") == "PRIZE":
            if prize_idx < len(names) and names[prize_idx]:
                g.wheel_slots[i] = {"type": "PRIZE", "name": str(names[prize_idx])[:30]}
            prize_idx += 1

    emit("toast", {"msg": f"Updated {min(prize_idx, len(names))} prize names."})
    broadcast(room)


@socketio.on("set_config")
def set_config(data):
    room = (data or {}).get("room", "main")
    g = get_game(room)
    if _get_sid() != g.host_sid:
        emit("toast", {"msg": "Host only."})
        return

    config = (data or {}).get("config", {})
    if not isinstance(config, dict):
        emit("toast", {"msg": "Invalid config."})
        return

    if "vowel_cost" in config:
        g.vowel_cost = int(config["vowel_cost"])
    if "final_seconds" in config:
        g.final_seconds = int(config["final_seconds"])
    if "final_jackpot" in config:
        g.final_jackpot = int(config["final_jackpot"])
    if "prize_replace_cash_values" in config:
        vals = config["prize_replace_cash_values"]
        if isinstance(vals, list):
            g.prize_replace_cash_values = [int(v) for v in vals if isinstance(v, (int, float))]

    db_set_room_config(
        room,
        {
            "vowel_cost": g.vowel_cost,
            "final_seconds": g.final_seconds,
            "final_jackpot": g.final_jackpot,
            "prize_replace_cash_values": g.prize_replace_cash_values,
        },
    )
    emit("toast", {"msg": "Config saved."})
    broadcast(room)


@app.post("/api/import_packs")
def api_import_packs():
    room = request.args.get("room", "main")
    g = get_game(room)

    # Host only
    if g.host_sid != request.args.get("sid"):
        return jsonify({"ok": False, "error": "Host only"}), 403

    if "file" not in request.files:
        return jsonify({"ok": False, "error": "Missing file"}), 400

    f = request.files["file"]
    try:
        payload = json.load(f.stream)
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    packs = payload.get("packs")
    if not isinstance(packs, list) or not packs:
        return jsonify({"ok": False, "error": "JSON must contain packs: []"}), 400

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


if __name__ == "__main__":
    print(f"DB: {os.path.abspath(DB_PATH)}")
    print("Open: http://127.0.0.1:5000/?room=main")
    socketio.run(app, host="0.0.0.0", port=5000, debug=False)
