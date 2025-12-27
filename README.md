# Holiday Wheel 🎡
*A Wheel-of-Fortune–style holiday party game*

A browser-based, multiplayer **Wheel of Fortune–style** game designed for family gatherings, holidays, and parties. One device acts as the **host**, while players join from their own phones, tablets, or laptops on the same network.

> ⚠️ This project is for **personal / party use only** and is **not affiliated with or endorsed by Wheel of Fortune®, Sony, or any broadcaster**.

---

## ✨ Features

- 🎡 TV-style spinning wheel (cash, prizes, bankrupt, lose-a-turn)
- 👥 Multiple players (default 8, configurable by host)
- 🧑‍💼 Secure **Host Mode**
- 📱 Mobile-friendly clients
- 🧩 Puzzle packs stored in SQLite
- 📦 JSON puzzle-pack import (host-only)
- 🎁 Prize wedges that convert to cash after banking
- ⚡ Toss-Up rounds with auto-revealing letters
- 🏁 Final Round with RSTLNE + timed solve
- 🔒 Turn enforcement (only active player can act)

---

## 📁 Repository Structure

holiday-wheel/
├── app.py # Flask + Socket.IO backend
├── requirements.txt # Python dependencies
├── puzzles.db # SQLite database (runtime)
├── templates/
│ └── index.html # Main UI
├── static/
│ ├── app.js # Frontend logic
│ └── styles.css # Styling
├── README.md
└── LICENSE


---

## 🧰 Requirements

- **Python 3.11+** (Linux strongly recommended)
- Modern browser (Chrome, Firefox, Safari)
- Devices on the same local network

> ⚠️ Python 3.14 on Windows may fail to build networking libraries  
> ✔️ Linux hosting is recommended for stability

---

## 🚀 Setup (Local Development)

### 1) Clone the repository
```bash
git clone https://github.com/balllder/holiday-wheel.git
cd holiday-wheel
```
### 2) Create a virtual environment
```bash
python3 -m venv .venv
source .venv/bin/activate
```
### 3) Install dependencies
```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```
### 4) Run the server
```bash
python app.py
```
Open in a browser:

http://127.0.0.1:5000

📱 Playing on Phones / Tablets

    Find the host computer’s LAN IP:

        Linux/macOS: ip addr or ifconfig

        Windows: ipconfig

    Ensure the server is listening on 0.0.0.0:5000

    On phones/tablets (same Wi-Fi), open:

http://<HOST_IP>:5000

If it doesn’t load:

    Disable guest Wi-Fi isolation

    Allow TCP port 5000 in firewall

    Confirm devices are on the same subnet

🧑‍💼 Host Mode

    Click Host Mode

    Enter the host code (default: holiday)

    Unlocks admin controls:

        New Game / New Puzzle

        Start Toss-Up / Final Round

        Set players

        Import puzzle packs

        Configure game settings

🧩 Puzzle Packs (JSON Import)

Puzzle packs are stored in SQLite and selectable by name.
JSON format

{
  "packs": [
    {
      "name": "CHRISTMAS HARD",
      "puzzles": [
        { "category": "PHRASE", "answer": "HANGING STOCKINGS BY THE FIREPLACE" },
        { "category": "FOOD & DRINK", "answer": "HOT COCOA WITH MARSHMALLOWS" }
      ]
    }
  ]
}

Rules

    Answers should be ALL CAPS

    Letters and spaces only

    Use Wheel-style categories

🎮 Gameplay Notes
Prize Wedges

    Land on prize → must guess a correct consonant

    Correct → prize is banked

    Prize wedge converts to cash for the rest of the game

    Miss → prize lost, next player’s turn

Toss-Up

    Letters auto-reveal gradually (TV style)

    Players buzz in to take control

    First correct solve wins

Final Round

    Finalist chosen by highest total cash + prize value

    RSTLNE revealed automatically

    Finalist picks 3 consonants + 1 vowel

    Timed solve attempt

🛠 Troubleshooting
Buttons don’t respond

    Open browser dev tools (F12)

    Check console for JavaScript errors

    Confirm app.js and socket.io load successfully

Socket.IO protocol error

    Ensure frontend Socket.IO version matches backend

    Use pinned versions from requirements.txt

Wheel pointer mismatch

    Canvas scaling issue (mobile zoom/orientation)

    Refresh page or rotate device

🔧 Customization Ideas

    Add more holiday or seasonal puzzle packs

    Adjust toss-up reveal speed

    Add sound effects

    Customize wheel wedges and prize list

    Add pack export to JSON

📜 License

This project is licensed under the MIT License.
See LICENSE
for details.
