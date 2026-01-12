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

**reCAPTCHA v3 (optional):**
- `RECAPTCHA_SITE_KEY`: Google reCAPTCHA v3 site key
- `RECAPTCHA_SECRET_KEY`: Google reCAPTCHA v3 secret key
- `RECAPTCHA_MIN_SCORE`: Minimum score threshold (default: 0.5)

## Architecture

**Backend (app.py)**:
- Flask + Flask-SocketIO for HTTP and WebSocket handling
- SQLite database for puzzles, packs, room configuration, and users
- In-memory game state stored in `GAMES` dictionary (one `GameState` per room)
- Dynamic player system: players join/leave games rather than claiming pre-created slots
- 20+ WebSocket event handlers for real-time game actions (including `join_game`, `leave_game`)

**Authentication (auth.py)**:
- Flask Blueprint at `/auth` prefix
- Separate login (`/auth/login`) and register (`/auth/register`) pages
- User registration with email verification and password confirmation
- Optional reCAPTCHA v3 spam protection (score-based, invisible)
- Persistent login with 30-day remember-me cookies
- Session integration with Socket.IO for player claim persistence
- Host admin page (`/auth/admin`) for managing users, packs, and room config

**Supporting Modules**:
- `db_auth.py`: User database CRUD operations, admin functions
- `email_service.py`: SMTP email sending for verification

**Frontend (static/app.js + templates/index.html)**:
- Vanilla JavaScript with Socket.IO client
- Reactive UI updates via `state` socket events from server
- HTML5 canvas for wheel animation

**Auth Frontend (static/auth.js + static/lobby.js + static/admin.js)**:
- Login/register form handling
- Room lobby with active room browsing
- Admin panel for user/pack/config management

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

## TV-Authentic UI

**Puzzle Board:**
- 4-row layout matching TV show: 12, 14, 14, 12 spaces per row
- Blue board frame with green empty slots
- White letter tiles with black text when revealed
- Variable row widths handled by `ROW_WIDTHS` array in app.js

**Wheel:**
- Authentic color palette defined in `WHEEL_COLORS` array
- Special wedges evenly distributed via `shuffle_wheel_with_spacing()` in app.py
- BANKRUPT: black, LOSE A TURN: white, FREE PLAY: neon green, PRIZE: silver
- Downward-pointing indicator (CSS border-top triangle)

**Authentication:**
- Login required to access game rooms (`@login_required` decorator on main route)
- Players must be registered/verified users
- Player names come from user's `display_name`

## Code Organization

**app.py** (~1,500 lines):
- Lines 1-55: Imports and constants (including `BASE_WHEEL`)
- Lines 56-105: `shuffle_wheel_with_spacing()` for even special wedge distribution
- Lines 106-380: Database helper functions (puzzles, packs, config)
- Lines 380-620: `Player` and `GameState` dataclasses
- Lines 620-800: Flask app setup, auth registration, background tasks
- Lines 800-1450: WebSocket event handlers (including `join_game`, `leave_game`)
- Lines 1450-1500: REST API for bulk pack import

**auth.py** (~650 lines):
- Authentication blueprint with routes for login, register, verify, logout
- `login_required` decorator and `get_current_user()` helper
- `verify_recaptcha()` for reCAPTCHA v3 score validation
- Room listing API for lobby
- Admin routes: user management, pack management, room config
- Room management: add/remove players, delete rooms

**db_auth.py** (~245 lines):
- User CRUD: create, get by email/id/token, verify, update login
- Remember token management for persistent sessions
- Room activity tracking for lobby
- Admin functions: list all users, delete user, manually verify

**static/app.js** (~810 lines):
- Lines 1-125: Initialization, constants (`ROW_WIDTHS`, `WHEEL_COLORS`)
- Lines 325-355: Pack dropdown rendering
- Lines 355-445: Puzzle board rendering (4-row TV layout with variable widths)
- Lines 445-580: Wheel drawing with `getWedgeColor()`, `getTextColor()`, animations
- Lines 580-700: Event listeners (including join/leave game handlers)
- Lines 700-810: WebSocket event listeners

**static/auth.js** (~115 lines):
- Login form handler (if on login page)
- Register form handler with password confirmation validation
- reCAPTCHA v3 token retrieval via `grecaptcha.execute()`

**static/admin.js** (~525 lines):
- Host authentication
- User management (list, verify, delete, resend email)
- Pack management (list, create, import JSON, delete)
- Room config (load, save per room)

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
