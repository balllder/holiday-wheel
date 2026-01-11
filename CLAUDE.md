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

# Run tests with coverage
pytest tests/ -v --cov=app --cov-report=term-missing

# Lint
ruff check .

# Format
ruff format .

# Type check
mypy app.py

# Install pre-commit hooks
pre-commit install
```

## Environment Variables

**Core:**
- `HOST_CODE`: Host authentication password (default: "holiday")
- `DB_PATH`: SQLite database path (default: "puzzles.db")
- `SECRET_KEY`: Flask session secret (default: "dev")
- `CORS_ORIGINS`: Comma-separated allowed origins (default: "*")

**Email (for user registration):**
- `EMAIL_ENABLED`: Enable email sending (default: "false")
- `SMTP_HOST`: SMTP server hostname (default: "smtp.gmail.com")
- `SMTP_PORT`: SMTP server port (default: "587")
- `SMTP_USER`: SMTP username
- `SMTP_PASS`: SMTP password
- `FROM_EMAIL`: Sender email address (default: "noreply@holidaywheel.com")
- `BASE_URL`: Application base URL for email links (default: "http://localhost:5000")

## Architecture

**Backend (app.py)**:
- Flask + Flask-SocketIO for HTTP and WebSocket handling
- SQLite database for puzzles, packs, room configuration, and users
- In-memory game state stored in `GAMES` dictionary (one `GameState` per room)
- 20+ WebSocket event handlers for real-time game actions

**Authentication (auth.py)**:
- Flask Blueprint at `/auth` prefix
- User registration with email verification
- Persistent login with 30-day remember-me cookies
- Session integration with Socket.IO for player claim persistence

**Supporting Modules**:
- `db_auth.py`: User database CRUD operations
- `email_service.py`: SMTP email sending for verification

**Frontend (static/app.js + templates/index.html)**:
- Vanilla JavaScript with Socket.IO client
- Reactive UI updates via `state` socket events from server
- HTML5 canvas for wheel animation

**Auth Frontend (static/auth.js + static/lobby.js)**:
- Login/register form handling
- Room lobby with active room browsing

**Database Schema**:
- `packs`: Puzzle pack collections
- `puzzles`: Individual puzzles with category, answer, enabled flag, pack_id
- `used_puzzles`: Tracks per-room puzzle usage to prevent repetition
- `room_config`: Per-room game settings (vowel cost, jackpot, prize values)
- `users`: User accounts with email, password hash, verification status
- `rooms`: Room tracking for lobby (name, activity timestamp, player counts)

## Game Phases

- **Normal**: Standard gameplay - spin wheel, guess letters, buy vowels, solve
- **Tossup**: Rapid letter reveal - any player can buzz in to solve
- **Final**: Selected player picks 3 consonants + 1 vowel, then attempts solve

## Code Organization

**app.py** (~1,450 lines):
- Lines 1-55: Imports and constants
- Lines 56-336: Database helper functions (puzzles, packs, config)
- Lines 338-580: `Player` and `GameState` dataclasses
- Lines 582-750: Flask app setup, auth registration, background tasks
- Lines 752-1400: WebSocket event handlers
- Lines 1402-1450: REST API for bulk pack import

**auth.py** (~235 lines):
- Authentication blueprint with routes for login, register, verify, logout
- `login_required` decorator and `get_current_user()` helper
- Room listing API for lobby

**db_auth.py** (~190 lines):
- User CRUD: create, get by email/id/token, verify, update login
- Remember token management for persistent sessions
- Room activity tracking for lobby

**static/app.js** (~785 lines):
- Lines 1-100: Initialization and element references
- Lines 400-460: Puzzle board rendering with word wrapping
- Lines 460-520: Wheel animation
- Lines 520-700: Event listeners
- Lines 700-785: WebSocket event listeners

## CI/CD

GitHub Actions workflow (`.github/workflows/ci.yml`) runs on push/PR to main:
- **build**: Installs dependencies, checks syntax, lints with ruff, type checks with mypy, runs tests with coverage
- **docker**: Builds Docker image

Coverage reports are uploaded to [Codecov](https://codecov.io/gh/balllder/holiday-wheel).

## Tooling

- **ruff**: Linting and formatting (config in `pyproject.toml`)
- **mypy**: Type checking (config in `mypy.ini`)
- **pytest**: Testing with pytest-cov for coverage
- **pre-commit**: Git hooks for ruff and mypy (config in `.pre-commit-config.yaml`)
- **Dependabot**: Automated dependency updates weekly, minor/patch only - major versions ignored (config in `.github/dependabot.yml`)
