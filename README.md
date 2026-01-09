# Holiday Wheel of Fortune

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

**Docker:**
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

## How to Play

1. Open the app in a browser and enter a room name
2. One player authenticates as the host using the host code
3. Host manages the game: starting rounds, selecting players, advancing turns
4. Players take turns spinning the wheel, guessing letters, and solving puzzles
5. Buy vowels for a set cost, or solve the puzzle outright when ready

### Game Modes

- **Normal Round**: Spin the wheel, guess consonants, buy vowels, solve the puzzle
- **Tossup Round**: Letters reveal automatically - buzz in to solve
- **Final Round**: Pick 3 consonants and 1 vowel, then solve for the jackpot

## License

MIT
