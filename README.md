# Holiday Wheel (Wheel-of-Fortune style party game)

A browser-based, multiplayer “Wheel of Fortune”-style holiday party game with a **host** and up to **8+ players** connecting from their own devices on the same network.

> This project is intended for **at-home/party use** and is **not affiliated with Wheel of Fortune**.

---

## What’s in this repo

Core files and folders: :contentReference[oaicite:1]{index=1}

- `app.py` — Python backend (web server + game logic)
- `templates/` — HTML templates
- `static/` — frontend assets (JS/CSS/images)
- `puzzles.db` — SQLite database with puzzle packs
- `requirements.txt` — Python dependencies

The project includes Python + JavaScript + HTML + CSS. :contentReference[oaicite:2]{index=2}

---

## Features (gameplay)

Typical flow:
- One device “claims host”
- Players join from phones/tablets/laptops and “claim” a player slot
- Host sets up players, picks a puzzle pack, and starts rounds
- Players can only **spin/guess/solve** on their turn (enforced by the server)

Game modes supported (depending on what your current build exposes in the UI):
- Regular rounds (spin → guess consonant → bank winnings/prizes → keep turn if correct)
- Toss-Up (auto-reveal like the TV game)
- Final Round experience (host starts final, finalist is selected by total value)

Prize wedge behavior (as implemented in this project’s “TV-style” rules):
- If a player lands on a **Prize**, they must guess a correct consonant to “bank” it.
- If they miss, the prize is lost and play passes to the next player.
- When banked, the prize wedge converts to a randomized cash value for the rest of the game.

Puzzle packs:
- Puzzles are stored in SQLite (`puzzles.db`)
- Packs are selectable by the host from a dropdown
- Packs can be imported from JSON (host-only), if your build includes the import UI/endpoint.

---

## Requirements

- Python 3.11+ recommended (Linux hosting recommended)
- A modern browser for clients (Chrome/Safari/Firefox)

> If you previously tried Python 3.14 on Windows and hit dependency issues (gevent/eventlet builds), switch to Linux hosting and/or a supported Python version.

---

## Setup (local dev)

### 1) Clone
```bash
git clone https://github.com/balllder/holiday-wheel.git
cd holiday-wheel
```
### 2) Create a virtual environment

Linux/macOS:
```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows (Command Prompt):
```bat
py -m venv .venv
.venv\Scripts\activate.bat
```


