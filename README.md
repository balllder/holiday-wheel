# Holiday Wheel of Fortune

[![CI](https://github.com/balllder/holiday-wheel/actions/workflows/ci.yml/badge.svg)](https://github.com/balllder/holiday-wheel/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/balllder/holiday-wheel/graph/badge.svg)](https://codecov.io/gh/balllder/holiday-wheel)
[![Docker Hub](https://img.shields.io/docker/v/clockboy/holiday-wheel?label=Docker%20Hub)](https://hub.docker.com/r/clockboy/holiday-wheel)

A real-time multiplayer web game where players spin a wheel, guess letters, and solve word puzzles. Built with Flask and WebSockets for seamless multiplayer gameplay.

## Setup

### Prerequisites

- Python 3.8+

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/balllder/holiday-wheel.git
   cd holiday-wheel
   ```

2. Create a virtual environment (recommended):
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

**Development:**
```bash
python app.py
```
The server starts at http://localhost:5000

**Production:**
```bash
gunicorn --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker app:app
```

**Docker (from Docker Hub):**
```bash
docker run -d -p 5000:5000 -v ./data:/app/data clockboy/holiday-wheel
```

**Docker (from source):**
```bash
docker compose up -d
```

The database persists in the `./data` directory.

### Configuration

Set these environment variables to customize the application:

| Variable | Description | Default |
|----------|-------------|---------|
| `HOST_CODE` | Password for host authentication | `holiday` |
| `DB_PATH` | SQLite database file path | `puzzles.db` |
| `SECRET_KEY` | Flask session secret key | `dev` |
| `CORS_ORIGINS` | Comma-separated allowed CORS origins | `*` |

**Email Configuration** (for user registration):

| Variable | Description | Default |
|----------|-------------|---------|
| `EMAIL_ENABLED` | Enable email sending | `false` |
| `SMTP_HOST` | SMTP server hostname | `smtp.gmail.com` |
| `SMTP_PORT` | SMTP server port | `587` |
| `SMTP_USER` | SMTP username | - |
| `SMTP_PASS` | SMTP password | - |
| `FROM_EMAIL` | Sender email address | `noreply@holidaywheel.com` |
| `BASE_URL` | Application base URL for email links | `http://localhost:5000` |

When `EMAIL_ENABLED=false`, verification links are printed to the console for development.

**reCAPTCHA Configuration** (optional spam protection):

| Variable | Description | Default |
|----------|-------------|---------|
| `RECAPTCHA_SITE_KEY` | Google reCAPTCHA v3 site key | - |
| `RECAPTCHA_SECRET_KEY` | Google reCAPTCHA v3 secret key | - |
| `RECAPTCHA_MIN_SCORE` | Minimum score to pass (0.0-1.0) | `0.5` |

When both keys are set, registration is protected by invisible reCAPTCHA v3. Get keys at https://www.google.com/recaptcha/admin (select reCAPTCHA v3)

## Features

### TV-Authentic UI

The game faithfully recreates the look and feel of the TV show:

**Puzzle Board:**
- 4-row layout matching the TV show (12, 14, 14, 12 spaces)
- Blue board frame with green empty slots
- White letter tiles with black text when revealed
- Automatic word wrapping and centering

**Wheel:**
- Authentic TV show color palette (red, blue, orange, gold, purple, pink, teal, etc.)
- Special wedges evenly distributed around the wheel (never clustered)
- BANKRUPT: black with silver text
- LOSE A TURN: white with black text
- FREE PLAY: neon green
- PRIZE: silver
- Downward-pointing indicator like the TV show

### User Authentication

- **Required Login**: Users must register and log in to access game rooms
- **Email Verification**: Verify email address before logging in
- **Spam Protection**: Optional invisible reCAPTCHA v3 on registration
- **Persistent Login**: Stay logged in for 30 days with remember-me cookies
- **Room Lobby**: Browse active rooms or create custom rooms
- **Dynamic Players**: Players join/leave games freely; names come from user accounts

### Host Admin Panel

A dedicated admin page (`/auth/admin`) for hosts to manage the game outside of active gameplay:

- **User Management**: View all users, verify accounts manually, resend verification emails, delete users
- **Room Management**: View active rooms, add/remove players, delete rooms
- **Puzzle Pack Management**: Create packs from text, import from JSON, delete packs
- **Room Configuration**: Configure vowel cost, final round settings, prize values, and active pack per room

Access requires logging in and authenticating with the host code. The in-game host admin section is only visible when host mode is active.

### Wheel Randomization

Wheel wedge positions are randomized when a room is created and each time a new game starts. Special wedges (BANKRUPT, LOSE A TURN, FREE PLAY, PRIZE) are evenly distributed around the wheel to prevent clustering, just like the TV show.

## How to Play

1. Register an account and verify your email
2. Log in and browse available rooms in the lobby
3. Join a room or enter a custom room name
4. Click "Join Game" to become a player (uses your display name)
5. One player authenticates as the host using the host code (default: `holiday`)
6. Host manages the game: starting rounds, loading puzzles, advancing turns
7. Players take turns spinning the wheel, guessing letters, and solving puzzles
8. Buy vowels for $250, or solve the puzzle outright when ready

### Game Modes

- **Normal Round**: Spin the wheel, guess consonants, buy vowels, solve the puzzle
- **Tossup Round**: Letters reveal automatically - buzz in to solve
- **Final Round**: Pick 3 consonants and 1 vowel, then solve for the jackpot

## License

MIT
