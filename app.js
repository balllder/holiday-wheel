const board = document.getElementById("board");
const badge = document.getElementById("countdownBadge");
const statusEl = document.getElementById("status");
const categoryEl = document.getElementById("category");
const usedEl = document.getElementById("usedLetters");

const spinBtn = document.getElementById("spinBtn");
const guessBtn = document.getElementById("guessBtn");
const solveBtn = document.getElementById("solveBtn");
const nextBtn = document.getElementById("nextBtn");
const newBtn = document.getElementById("newBtn");

const letterInput = document.getElementById("letterInput");
const solveInput = document.getElementById("solveInput");

const playersEl = document.getElementById("players");
const playersInput = document.getElementById("playersInput");
const setPlayersBtn = document.getElementById("setPlayersBtn");

const startTimerBtn = document.getElementById("startTimerBtn");
const stopTimerBtn = document.getElementById("stopTimerBtn");
const timerText = document.getElementById("timerText");

let players = ["Player 1","Player 2","Player 3","Player 4"].map(n=>({name:n,total:0}));
let active = 0;

let puzzle = "HAPPY HOLIDAYS";
let revealed = new Set();
let used = new Set();

let timer = null;
let timeLeft = 0;

function renderBoard(){
  board.innerHTML="";
  for(const c of puzzle){
    const d=document.createElement("div");
    d.className="tile";
    if(c===" "){ d.classList.add("space"); }
    else if(revealed.has(c)){ d.textContent=c; }
    else d.classList.add("hidden");
    board.appendChild(d);
  }
  categoryEl.textContent="Category: Phrase";
  usedEl.textContent="Used: "+([...used].join(" ")||"—");
}

function renderPlayers(){
  playersEl.innerHTML="";
  players.forEach((p,i)=>{
    const d=document.createElement("div");
    d.className="player"+(i===active?" active":"");
    d.innerHTML=`<b>${p.name}</b><br>$${p.total}`;
    playersEl.appendChild(d);
  });
}

function startTimer(){
  if(timer) return;
  timeLeft=30;
  badge.classList.remove("hidden");
  badge.textContent=timeLeft;
  timerText.textContent="30s";

  timer=setInterval(()=>{
    timeLeft--;
    badge.textContent=timeLeft;
    timerText.textContent=timeLeft+"s";
    if(timeLeft<=0){
      clearInterval(timer);
      timer=null;
      statusEl.textContent="TIME!";
    }
  },1000);
}

spinBtn.onclick=()=>statusEl.textContent="Spin!";
guessBtn.onclick=()=>{
  const l=letterInput.value.toUpperCase();
  letterInput.value="";
  if(!l||used.has(l))return;
  used.add(l);
  if(puzzle.includes(l))revealed.add(l);
  renderBoard();
};
solveBtn.onclick=()=>{
  if(solveInput.value.toUpperCase()===puzzle){
    statusEl.textContent="Solved!";
    players[active].total+=1000;
    revealed=new Set(puzzle.replace(/ /g,"").split(""));
    renderBoard();
    renderPlayers();
  } else statusEl.textContent="Wrong!";
};
nextBtn.onclick=()=>{active=(active+1)%players.length;renderPlayers()};
newBtn.onclick=()=>{revealed.clear();used.clear();renderBoard()};
startTimerBtn.onclick=startTimer;
stopTimerBtn.onclick=()=>{clearInterval(timer);timer=null;badge.classList.add("hidden")};

setPlayersBtn.onclick=()=>{
  const names=playersInput.value.split(",").map(s=>s.trim()).filter(Boolean);
  if(!names.length)return;
  players=names.map(n=>({name:n,total:0}));
  active=0;
  renderPlayers();
};

renderBoard();
renderPlayers();
