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

### User Authentication

- **Registration**: Dedicated registration page with password confirmation
- **Email Verification**: Verify email address before logging in
- **Spam Protection**: Optional invisible reCAPTCHA v3 on registration
- **Persistent Login**: Stay logged in for 30 days with remember-me cookies
- **Room Lobby**: Browse active rooms or create custom rooms
- **Player Claiming**: Authenticated users can claim player slots that persist across reconnections

### Wheel Randomization

Wheel wedge positions are randomized when a room is created and each time a new game starts, ensuring variety in gameplay.

## How to Play

1. Register an account and verify your email (or play as guest)
2. Browse available rooms in the lobby or enter a custom room name
3. Claim a player slot by entering your name
4. One player authenticates as the host using the host code
5. Host manages the game: starting rounds, selecting players, advancing turns
6. Players take turns spinning the wheel, guessing letters, and solving puzzles
7. Buy vowels for a set cost, or solve the puzzle outright when ready

### Game Modes

- **Normal Round**: Spin the wheel, guess consonants, buy vowels, solve the puzzle
- **Tossup Round**: Letters reveal automatically - buzz in to solve
- **Final Round**: Pick 3 consonants and 1 vowel, then solve for the jackpot

## License

MIT
