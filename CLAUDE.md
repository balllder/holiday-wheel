# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Holiday Wheel of Fortune - A real-time multiplayer web game built with Flask and WebSockets. Players spin a wheel, guess letters, and solve word puzzles in room-based game sessions.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run development server (port 5000)
python app.py

# Run production server
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker app:app

# Run with Docker
docker compose up -d

# Run tests
pytest tests/ -v
```

## Environment Variables

- `HOST_CODE`: Host authentication password (default: "holiday")
- `DB_PATH`: SQLite database path (default: "puzzles.db")
- `SECRET_KEY`: Flask session secret (default: "dev")
- `CORS_ORIGINS`: Comma-separated allowed origins (default: "*")

## Architecture

**Backend (app.py)**:
- Flask + Flask-SocketIO for HTTP and WebSocket handling
- SQLite database for puzzles, packs, and room configuration
- In-memory game state stored in `GAMES` dictionary (one `GameState` per room)
- 14 WebSocket event handlers for real-time game actions

**Frontend (static/app.js + templates/index.html)**:
- Vanilla JavaScript with Socket.IO client
- Reactive UI updates via `state` socket events from server
- HTML5 canvas for wheel animation

**Database Schema**:
- `packs`: Puzzle pack collections
- `puzzles`: Individual puzzles with category, answer, enabled flag, pack_id
- `used_puzzles`: Tracks per-room puzzle usage to prevent repetition
- `room_config`: Per-room game settings (vowel cost, jackpot, prize values)

## Game Phases

- **Normal**: Standard gameplay - spin wheel, guess letters, buy vowels, solve
- **Tossup**: Rapid letter reveal - any player can buzz in to solve
- **Final**: Selected player picks 3 consonants + 1 vowel, then attempts solve

## Code Organization

**app.py** (1,128 lines):
- Lines 54-331: Database helper functions
- Lines 336-573: `Player` and `GameState` dataclasses
- Lines 576-727: Flask app setup and background tasks
- Lines 729-1077: WebSocket event handlers
- Lines 1078-1122: REST API for bulk pack import

**static/app.js** (728 lines):
- Lines 1-100: Initialization and element references
- Lines 394-450: Puzzle board rendering with word wrapping
- Lines 452-511: Wheel animation
- Lines 515-648: Event listeners
- Lines 649-727: WebSocket event listeners

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push/PR to main:
- **build**: Installs dependencies, checks Python syntax, runs tests
- **docker**: Builds Docker image
