/* global io */
const ROOM = window.__ROOM__ || "main";
const socket = io({ transports: ["websocket", "polling"] });

const el = (id) => document.getElementById(id);

const els = {
  roomLabel: el("roomLabel"),
  packCount: el("packCount"),
  phasePill: el("phasePill"),
  category: el("category"),
  usedLetters: el("usedLetters"),
  status: el("status"),
  board: el("vannaBoard"),

  connDot: el("connDot"),
  connText: el("connText"),

  hostBanner: el("hostBanner"),
  hostStatus: el("hostStatus"),

  joinGameBtn: el("joinGameBtn"),
  leaveGameBtn: el("leaveGameBtn"),

  letterInput: el("letterInput"),
  guessBtn: el("guessBtn"),
  vowelSelect: el("vowelSelect"),
  buyVowelBtn: el("buyVowelBtn"),
  solveInput: el("solveInput"),
  solveBtn: el("solveBtn"),
  buzzBtn: el("buzzBtn"),

  spinBtn: el("spinBtn"),
  wedgeValue: el("wedgeValue"),
  roundScore: el("roundScore"),
  prizeMini: el("prizeMini"),

  players: el("players"),

  // final UI
  finalCountdownWrap: el("finalCountdownWrap"),
  finalCountdown: el("finalCountdown"),
  finalPicker: el("finalPicker"),
  finalConsonants: el("finalConsonants"),
  finalVowel: el("finalVowel"),
  finalPickInput: el("finalPickInput"),
  finalPickConBtn: el("finalPickConBtn"),
  finalPickVowelBtn: el("finalPickVowelBtn"),
  finalPickHint: el("finalPickHint"),
  normalGuessRow: el("normalGuessRow"),

  // host UI
  hostBtn: el("hostBtn"),
  hostModal: el("hostModal"),
  hostModalCard: el("hostModalCard"),
  closeHostModal: el("closeHostModal"),
  hostCode: el("hostCode"),
  claimHostBtn: el("claimHostBtn"),
  releaseHostBtn: el("releaseHostBtn"),

  newGameBtn: el("newGameBtn"),
  newPuzzleBtn: el("newPuzzleBtn"),
  startTossupBtn: el("startTossupBtn"),
  endTossupBtn: el("endTossupBtn"),
  startFinalBtn: el("startFinalBtn"),
  endFinalBtn: el("endFinalBtn"),

  setPlayersBtn: el("setPlayersBtn"),
  playersInput: el("playersInput"),

  // pack UI
  packSelect: el("packSelect"),
  refreshPacksBtn: el("refreshPacksBtn"),

  prizeNamesText: el("prizeNamesText"),
  setPrizeNamesBtn: el("setPrizeNamesBtn"),

  hostSetActiveSelect: el("hostSetActiveSelect"),
  hostSetActiveBtn: el("hostSetActiveBtn"),
  hostAdminDetails: el("hostAdminDetails"),

  wheel: el("wheel"),
  themeToggle: el("themeToggle"),
  themeIcon: el("themeIcon"),
};

/* Theme toggle */
function initTheme(){
  const saved = localStorage.getItem("theme");
  if(saved === "light"){
    document.documentElement.setAttribute("data-theme", "light");
    els.themeIcon.textContent = "🌙";
  }
}
function toggleTheme(){
  const current = document.documentElement.getAttribute("data-theme");
  if(current === "light"){
    document.documentElement.removeAttribute("data-theme");
    localStorage.setItem("theme", "dark");
    els.themeIcon.textContent = "☀️";
  } else {
    document.documentElement.setAttribute("data-theme", "light");
    localStorage.setItem("theme", "light");
    els.themeIcon.textContent = "🌙";
  }
}
initTheme();
els.themeToggle.addEventListener("click", toggleTheme);

/* Logout handler */
document.getElementById("logoutBtn")?.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.href = "/auth/login";
});

els.roomLabel.textContent = ROOM;

const BOARD_ROWS = 4;
const ROW_WIDTHS = [12, 14, 14, 12]; // Real Wheel of Fortune layout
const MAX_ROW_WIDTH = Math.max(...ROW_WIDTHS);
const VOWELS = new Set(["A","E","I","O","U"]);
const ALPHA = /^[A-Z]$/;

let state = null;
let myPlayerIdx = null;
let iAmHost = false;

function toast(msg){
  els.status.textContent = msg || "";
}

function setConn(status){
  els.connDot.classList.remove("on","off","warn");
  if(status === "on"){
    els.connDot.classList.add("on");
    els.connText.textContent = "Connected";
  } else if(status === "warn"){
    els.connDot.classList.add("warn");
    els.connText.textContent = "Reconnecting…";
  } else {
    els.connDot.classList.add("off");
    els.connText.textContent = "Disconnected";
  }
}

function normalizeLetter(ch){
  ch = (ch||"").toUpperCase().trim();
  return ALPHA.test(ch) ? ch : "";
}

function updateHostUI(){
  if(iAmHost) els.hostBanner.classList.remove("hidden");
  else els.hostBanner.classList.add("hidden");

  // Show/hide host admin section
  if(iAmHost) els.hostAdminDetails?.classList.remove("hidden");
  else els.hostAdminDetails?.classList.add("hidden");

  const hostButtons = document.querySelectorAll(".hostOnly");
  hostButtons.forEach(btn=>{
    btn.disabled = !iAmHost;
    btn.title = !iAmHost ? "Host only" : "";
  });

  if(state?.host){
    els.hostStatus.textContent = `Host: ${state.host.claimed ? (iAmHost ? "claimed (this device)" : "claimed") : "open"}`;
  } else {
    els.hostStatus.textContent = "Host: —";
  }
}

function isMyTurnNormal(){
  return state && state.phase === "normal" && typeof state.active_idx === "number" && myPlayerIdx === state.active_idx;
}

function isTossupController(){
  if(!state || state.phase !== "tossup") return false;
  const controllerIdx = state.tossup?.controller_player_idx;
  return typeof controllerIdx === "number" && controllerIdx === myPlayerIdx;
}

function isFinalActive(){
  return state && state.phase === "final" && typeof state.active_idx === "number" && myPlayerIdx === state.active_idx;
}

function canBuzzNow(){
  if(!state || state.phase !== "tossup") return false;
  if(myPlayerIdx == null) return false;

  const locked = (state.tossup?.locked_player_idxs || []).includes(myPlayerIdx);
  if(locked) return false;

  const controllerExists = typeof state.tossup?.controller_player_idx === "number";
  if(controllerExists) return false;

  const allowed = state.tossup?.allowed_player_idxs;
  if(Array.isArray(allowed) && allowed.length > 0){
    return allowed.includes(myPlayerIdx);
  }
  return true;
}

function updateTurnGating(){
  const phase = state?.phase || "normal";

  if(phase === "normal"){
    const myTurn = isMyTurnNormal();
    els.spinBtn.disabled = !myTurn;
    els.guessBtn.disabled = !myTurn;
    els.buyVowelBtn.disabled = !myTurn;
    els.solveBtn.disabled = !myTurn;
    els.buzzBtn.disabled = true;
    return;
  }

  if(phase === "tossup"){
    els.spinBtn.disabled = true;
    els.guessBtn.disabled = true;
    els.buyVowelBtn.disabled = true;

    const controller = isTossupController();
    els.solveBtn.disabled = !controller;

    els.buzzBtn.disabled = !canBuzzNow();
    return;
  }

  if(phase === "final"){
    els.spinBtn.disabled = true;
    els.guessBtn.disabled = true;
    els.buyVowelBtn.disabled = true;
    els.buzzBtn.disabled = true;

    els.solveBtn.disabled = !isFinalActive();
    return;
  }

  els.spinBtn.disabled = true;
  els.guessBtn.disabled = true;
  els.buyVowelBtn.disabled = true;
  els.buzzBtn.disabled = true;
  els.solveBtn.disabled = true;
}

function shortPrizeName(name){
  const s = String(name || "PRIZE").trim().toUpperCase();
  const parts = s.split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return parts.join(" ");
  if (s.includes("GIFT") && s.includes("CARD")) return "GIFT CARD";
  return `${parts[0]} ${parts[1][0]}.`;
}

function labelForSlot(w){
  if(typeof w === "number") return `$${w}`;
  if(typeof w === "string") return w;
  if(typeof w === "object" && w.type === "PRIZE") return shortPrizeName(w.name);
  return String(w);
}

function wedgeLabel(w){
  if(w == null) return "—";
  if(typeof w === "number") return `$${w}`;
  if(typeof w === "string") return w;
  if(typeof w === "object" && w.type === "PRIZE") return `PRIZE: ${w.name}`;
  return String(w);
}

/* ---------- Final UI ---------- */
function renderFinalUI(){
  const isFinal = state?.phase === "final";
  els.finalCountdownWrap.classList.toggle("hidden", !isFinal);

  const hideNormalGuess = (state?.phase === "final" || state?.phase === "tossup");
  els.normalGuessRow.classList.toggle("hidden", hideNormalGuess);

  if(!isFinal){
    els.finalPicker.classList.add("hidden");
    return;
  }

  const rem = state?.final?.remaining_seconds;
  els.finalCountdown.textContent = (typeof rem === "number") ? String(rem) : "—";

  const stage = state?.final?.stage || "pick";
  const picks = state?.final?.picks || { consonants: [], vowel: null };

  const showPicker = isFinalActive() && stage === "pick";
  els.finalPicker.classList.toggle("hidden", !showPicker);

  els.finalConsonants.textContent = picks.consonants?.length ? picks.consonants.join(" ") : "—";
  els.finalVowel.textContent = picks.vowel ? picks.vowel : "—";

  if(showPicker){
    const needCons = 3 - (picks.consonants?.length || 0);
    const needV = picks.vowel ? 0 : 1;
    els.finalPickHint.textContent = `Need: ${needCons} consonant(s), ${needV} vowel.`;
    els.finalPickConBtn.disabled = needCons <= 0;
    els.finalPickVowelBtn.disabled = needV <= 0;
  }
}

els.finalPickConBtn?.addEventListener("click", ()=>{
  const l = normalizeLetter(els.finalPickInput.value);
  els.finalPickInput.value = "";
  if(!l) return;
  socket.emit("final_pick", { room: ROOM, kind: "consonant", letter: l });
});

els.finalPickVowelBtn?.addEventListener("click", ()=>{
  const l = normalizeLetter(els.finalPickInput.value);
  els.finalPickInput.value = "";
  if(!l) return;
  socket.emit("final_pick", { room: ROOM, kind: "vowel", letter: l });
});

els.finalPickInput?.addEventListener("keydown", (e)=>{
  if(e.key !== "Enter") return;
  const l = normalizeLetter(els.finalPickInput.value);
  if(!l) return;
  const picks = state?.final?.picks || { consonants: [], vowel: null };
  const kind = (VOWELS.has(l) && !picks.vowel) ? "vowel" : "consonant";
  socket.emit("final_pick", { room: ROOM, kind, letter: l });
  els.finalPickInput.value = "";
});

/* ---------- Packs UI ---------- */
function renderPackDropdown(){
  if(!els.packSelect) return;
  const packs = state?.packs || [];
  const active = state?.active_pack_id ?? null;

  const opts = [`<option value="">All Packs</option>`].concat(
    packs.map(p => `<option value="${p.id}">${p.name}</option>`)
  );
  els.packSelect.innerHTML = opts.join("");

  if(active == null){
    els.packSelect.value = "";
  } else {
    els.packSelect.value = String(active);
  }
}

els.refreshPacksBtn?.addEventListener("click", ()=>{
  if(!iAmHost) return;
  socket.emit("list_packs", { room: ROOM });
});

els.packSelect?.addEventListener("change", ()=>{
  if(!iAmHost) return;
  const v = els.packSelect.value; // "" = all
  socket.emit("set_active_pack", { room: ROOM, pack_id: v === "" ? null : Number(v) });
});


/* ---------- Board ---------- */
function wrapWordsToLines(answer){
  const words = answer.trim().replace(/\s+/g," ").split(" ").filter(Boolean);
  const lines = [];
  let cur = "";
  let lineIdx = 0;
  for(const w of words){
    const maxW = ROW_WIDTHS[Math.min(lineIdx, BOARD_ROWS-1)];
    if(!cur){ cur = w; continue; }
    if(cur.length + 1 + w.length <= maxW) cur = cur + " " + w;
    else {
      lines.push(cur);
      lineIdx++;
      cur = w;
    }
  }
  if(cur) lines.push(cur);
  while(lines.length > BOARD_ROWS){
    const last = lines.pop();
    const maxW = ROW_WIDTHS[BOARD_ROWS-1];
    lines[lines.length-1] = (lines[lines.length-1] + " " + last).slice(0, maxW);
  }
  while(lines.length < BOARD_ROWS) lines.push("");
  return lines.map((l, i) => {
    const maxW = ROW_WIDTHS[i];
    return l.length > maxW ? l.slice(0, maxW) : l;
  });
}

function layoutToGrid(answer){
  const lines = wrapWordsToLines(answer);
  const grid = [];
  for(let r=0;r<BOARD_ROWS;r++){
    const rowWidth = ROW_WIDTHS[r];
    const line = lines[r];
    const row = Array.from({length:rowWidth}, ()=>null);
    const padLeft = Math.max(0, Math.floor((rowWidth - line.length)/2));
    for(let i=0;i<line.length && (padLeft+i)<rowWidth;i++){
      row[padLeft+i] = line[i];
    }
    grid.push(row);
  }
  return grid;
}

function renderBoard(){
  const ans = (state?.puzzle?.answer || "").toUpperCase();
  const grid = layoutToGrid(ans);
  const revealed = new Set(state?.revealed || []);
  els.board.innerHTML = "";

  for(let r=0;r<BOARD_ROWS;r++){
    const rowWidth = ROW_WIDTHS[r];
    const rowDiv = document.createElement("div");
    rowDiv.className = "vRow";

    for(let c=0;c<rowWidth;c++){
      const v = grid[r][c];
      const cell = document.createElement("div");
      cell.className = "vCell";

      if(v === null){
        // Empty slot - green background (no puzzle letter here)
        cell.classList.add("empty");
      } else if(v === " "){
        // Space between words - green background
        cell.classList.add("space");
      } else if(ALPHA.test(v)){
        // Letter tile
        if(revealed.has(v)){
          // Revealed - white background, black text
          cell.classList.add("revealed");
          cell.textContent = v;
        } else {
          // Hidden - white background, no text
          cell.classList.add("hiddenTile");
        }
      } else {
        // Punctuation or special characters
        cell.classList.add("revealed");
        cell.textContent = v;
      }
      rowDiv.appendChild(cell);
    }
    els.board.appendChild(rowDiv);
  }
}

/* ---------- Wheel drawing ---------- */
const ctx = els.wheel.getContext("2d");
let wheelAngle = 0;
let wheelAnim = null;

// Authentic Wheel of Fortune TV show colors
const WHEEL_COLORS = [
  "#c41e3a", // Cherry Red
  "#0047ab", // Royal Blue
  "#ff8c00", // Dark Orange
  "#ffcc00", // Golden Yellow
  "#9932cc", // Purple
  "#ff1493", // Pink
  "#008b8b", // Teal
  "#dc143c", // Crimson
  "#4169e1", // Royal Blue 2
  "#ff4500", // Orange Red
  "#32cd32", // Lime Green
  "#9400d3", // Violet
  "#ff69b4", // Hot Pink
  "#1e90ff", // Dodger Blue
  "#ffd700", // Gold
  "#00ced1", // Dark Turquoise
  "#ff6347", // Tomato
  "#8a2be2", // Blue Violet
  "#00fa9a", // Medium Spring Green
  "#ff7f50", // Coral
];

/* Responsive wheel sizing */
function resizeWheel(){
  const container = els.wheel.parentElement;
  const maxSize = 360;
  const minSize = 200;
  const containerWidth = container.clientWidth - 24; // account for padding
  const size = Math.max(minSize, Math.min(maxSize, containerWidth));

  if(els.wheel.width !== size || els.wheel.height !== size){
    els.wheel.width = size;
    els.wheel.height = size;
    // Redraw after resize
    if(state?.wheel_slots){
      const labels = state.wheel_slots.map(labelForSlot);
      drawWheel(labels, state.wheel_slots);
    }
  }
}

let resizeTimeout;
window.addEventListener("resize", ()=>{
  clearTimeout(resizeTimeout);
  resizeTimeout = setTimeout(resizeWheel, 100);
});

function getWedgeColor(slot, index){
  // Authentic TV show special wedge colors
  if(slot === "BANKRUPT") return "#000000"; // Pure Black
  if(slot === "LOSE A TURN") return "#ffffff"; // White
  if(slot === "FREE PLAY") return "#39ff14"; // Neon Green (TV show style)
  if(typeof slot === "object" && slot?.type === "PRIZE") return "#c0c0c0"; // Silver for prize tags
  // Cycle through colors for cash values
  return WHEEL_COLORS[index % WHEEL_COLORS.length];
}

function getTextColor(slot){
  // Authentic TV show text colors
  if(slot === "BANKRUPT") return "#c0c0c0"; // Silver text on black
  if(slot === "LOSE A TURN") return "#000000"; // Black text on white
  if(slot === "FREE PLAY") return "#003300"; // Dark green text
  if(typeof slot === "object" && slot?.type === "PRIZE") return "#333333"; // Dark text on silver
  // White text for all others
  return "#ffffff";
}

function drawWheel(labels, slots){
  const n = labels.length || 1;
  const arc = (Math.PI * 2) / n;
  const cx = els.wheel.width/2, cy = els.wheel.height/2;
  const radius = Math.min(cx,cy)-6;
  const fontSize = Math.max(10, Math.floor(els.wheel.width / 26));

  ctx.clearRect(0,0,els.wheel.width,els.wheel.height);

  for(let i=0;i<n;i++){
    const start = wheelAngle + i*arc;
    const end = start + arc;
    const slot = slots ? slots[i] : null;

    ctx.beginPath();
    ctx.moveTo(cx,cy);
    ctx.arc(cx,cy,radius,start,end);
    ctx.closePath();
    ctx.fillStyle = getWedgeColor(slot, i);
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,.3)";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.save();
    ctx.translate(cx,cy);
    ctx.rotate(start+arc/2);
    ctx.textAlign="right";
    ctx.fillStyle = getTextColor(slot);
    ctx.font=`bold ${fontSize}px system-ui`;
    ctx.shadowColor = "rgba(0,0,0,.5)";
    ctx.shadowBlur = 2;
    ctx.shadowOffsetX = 1;
    ctx.shadowOffsetY = 1;
    ctx.fillText(String(labels[i]), radius-12, 5);
    ctx.restore();
  }
}

function spinToIndex(targetIndex, labels, slots){
  const n = labels.length;
  if(!n) return;

  const arc = (Math.PI * 2) / n;
  const desiredWheelAngle = (-Math.PI / 2) - (targetIndex * arc) - (arc / 2);
  const extraSpins = Math.PI * 2 * (3 + Math.floor(Math.random() * 3));
  const start = wheelAngle;
  const target = desiredWheelAngle - extraSpins;

  const duration = 1100;
  const t0 = performance.now();
  if(wheelAnim) cancelAnimationFrame(wheelAnim);

  function step(now){
    const t = Math.min(1, (now - t0) / duration);
    const ease = 1 - Math.pow(1 - t, 3);
    wheelAngle = start + (target - start) * ease;
    drawWheel(labels, slots);
    if(t < 1) wheelAnim = requestAnimationFrame(step);
  }
  wheelAnim = requestAnimationFrame(step);
}

resizeWheel();
drawWheel(["…"]);

/* ---------- Players + joining ---------- */
function renderPlayers(){
  els.players.innerHTML = "";

  // Update join/leave button visibility
  const hasJoined = myPlayerIdx !== null;
  els.joinGameBtn.style.display = hasJoined ? "none" : "";
  els.leaveGameBtn.style.display = hasJoined ? "" : "none";

  if(els.hostSetActiveSelect){
    const cur = els.hostSetActiveSelect.value;
    els.hostSetActiveSelect.innerHTML = `<option value="">Choose player…</option>` +
      (state?.players || []).map((p,i)=>`<option value="${i}">${i+1}: ${p.name}</option>`).join("");
    if(cur !== "" && Number(cur) < (state?.players || []).length){
      els.hostSetActiveSelect.value = cur;
    }
  }

  if ((state?.players || []).length === 0) {
    els.players.innerHTML = `<div class="muted">No players yet. Click "Join Game" to play!</div>`;
    return;
  }

  (state?.players || []).forEach((p, idx)=>{
    const d = document.createElement("div");
    d.className = "player" + (idx===state.active_idx ? " active" : "");

    const perm = (p.prizes && p.prizes.length)
      ? p.prizes.map(x => (typeof x === "string") ? x : `${x.name} ($${x.value||0})`).join(", ")
      : "—";
    const permVal = p.prize_value_total ?? 0;

    const roundPr = (p.round_prizes && p.round_prizes.length)
      ? p.round_prizes.map(x => (typeof x === "string") ? x : `${x.name} ($${x.value||0})`).join(", ")
      : "—";
    const roundVal = p.round_prize_value_total ?? 0;

    const mineTag = (myPlayerIdx === idx) ? `<span class="tag">You</span>` : "";

    d.innerHTML = `
      <b>${p.name}${idx===state.active_idx ? " ✅" : ""}</b>
      <div>${mineTag}</div>
      <div class="muted small">Total cash: $${p.total}</div>
      <div class="muted small">Prize value: $${permVal}</div>
      <div class="muted small">Prizes: ${perm}</div>
      <div class="muted small">Round: $${p.round_bank} • Round prizes ($${roundVal}): ${roundPr}</div>
    `;

    els.players.appendChild(d);
  });
}

/* ---------- Host modal ---------- */
function openHostModal(){
  els.hostModal.classList.add("show");
  els.hostModal.setAttribute("aria-hidden", "false");
}
function closeHostModal(){
  els.hostModal.classList.remove("show");
  els.hostModal.setAttribute("aria-hidden", "true");
}
closeHostModal();

els.hostBtn.addEventListener("click", openHostModal);
els.closeHostModal.addEventListener("click", closeHostModal);
els.hostModal.addEventListener("click", (e)=>{
  if(e.target === els.hostModal) closeHostModal();
});
els.hostModalCard.addEventListener("click", (e)=>e.stopPropagation());

els.claimHostBtn.addEventListener("click", ()=>{
  const code = (els.hostCode.value||"").trim();
  socket.emit("claim_host", { room: ROOM, code });
});
els.releaseHostBtn.addEventListener("click", ()=>{
  socket.emit("release_host", { room: ROOM });
});

/* ---------- Controls ---------- */
els.spinBtn.addEventListener("click", ()=>{
  els.status.textContent = "";
  socket.emit("spin", { room: ROOM });
});
els.buzzBtn.addEventListener("click", ()=> socket.emit("buzz", { room: ROOM }));

els.guessBtn.addEventListener("click", ()=>{
  const l = normalizeLetter(els.letterInput.value);
  els.letterInput.value = "";
  if(!l) return;
  socket.emit("guess", { room: ROOM, letter: l });
});

els.buyVowelBtn.addEventListener("click", ()=>{
  const v = normalizeLetter(els.vowelSelect.value);
  if(!v || !VOWELS.has(v)) { toast("Pick a vowel first."); return; }
  socket.emit("guess", { room: ROOM, letter: v });
  els.vowelSelect.value = "";
});

els.solveBtn.addEventListener("click", ()=>{
  const attempt = (els.solveInput.value || "").trim();
  if(!attempt) return;
  socket.emit("solve", { room: ROOM, attempt });
  els.solveInput.value = "";
});

els.letterInput.addEventListener("keydown", (e)=>{ if(e.key==="Enter") els.guessBtn.click(); });
els.solveInput.addEventListener("keydown", (e)=>{ if(e.key==="Enter") els.solveBtn.click(); });

els.joinGameBtn.addEventListener("click", ()=>{
  socket.emit("join_game", { room: ROOM });
});

els.leaveGameBtn.addEventListener("click", ()=>{
  socket.emit("leave_game", { room: ROOM });
});

// host admin
els.setPlayersBtn?.addEventListener("click", ()=>{
  const names = (els.playersInput.value||"").split(",").map(s=>s.trim()).filter(Boolean);
  socket.emit("set_players", { room: ROOM, names });
});
els.newGameBtn?.addEventListener("click", ()=> socket.emit("new_game", { room: ROOM }));
els.newPuzzleBtn?.addEventListener("click", ()=> socket.emit("new_puzzle", { room: ROOM }));
els.startTossupBtn?.addEventListener("click", ()=> socket.emit("start_tossup", { room: ROOM }));
els.endTossupBtn?.addEventListener("click", ()=> socket.emit("end_tossup", { room: ROOM }));
els.startFinalBtn?.addEventListener("click", ()=> socket.emit("start_final", { room: ROOM }));
els.endFinalBtn?.addEventListener("click", ()=> socket.emit("end_final", { room: ROOM }));

els.hostSetActiveBtn?.addEventListener("click", ()=>{
  if(!iAmHost) return;
  const v = els.hostSetActiveSelect.value;
  if(v === "") return;
  socket.emit("set_active_player", { room: ROOM, player_idx: Number(v) });
});

els.setPrizeNamesBtn?.addEventListener("click", ()=>{
  const names = (els.prizeNamesText.value || "").split("\n").map(s=>s.trim()).filter(Boolean);
  socket.emit("set_prize_names", { room: ROOM, names });
});

/* ---------- Socket events ---------- */
socket.on("connect", ()=>{
  setConn("on");
  socket.emit("join", { room: ROOM });
  socket.emit("list_packs", { room: ROOM });
});
socket.on("disconnect", ()=> setConn("off"));
socket.io.on("reconnect_attempt", ()=> setConn("warn"));
socket.on("connect_error", (e)=>{
  setConn("off");
  console.error("connect_error", e);
  toast("Connection error (see console).");
});

socket.on("you", (d)=>{
  myPlayerIdx = (d && typeof d.player_idx === "number") ? d.player_idx : null;
  updateTurnGating();
  renderPlayers();
  renderFinalUI();
});

socket.on("host_granted", (d)=>{
  iAmHost = !!d?.granted;
  updateHostUI();
  if(iAmHost) socket.emit("list_packs", { room: ROOM });
  toast(iAmHost ? "You are Host on this device." : "Host not active on this device.");
});

socket.on("toast", (d)=>toast(d?.msg || ""));

socket.on("packs", (d)=>{
  if(!state) state = {};
  state.packs = d?.packs || [];
  renderPackDropdown();
});

socket.on("state", (s)=>{
  const prevWheelIndex = state?.wheel_index;
  const prevPuzzleId = state?.puzzle?.id;
  state = s;

  // Clear guess inputs when puzzle changes
  if (prevPuzzleId !== undefined && state.puzzle?.id !== prevPuzzleId) {
    els.letterInput.value = "";
    els.solveInput.value = "";
  }

  els.phasePill.textContent = (state.phase || "normal").toUpperCase();

  const apName = state?.active_pack_name ? `Pack: ${state.active_pack_name}` : "Pack: ALL";
  if (state.db) {
    els.packCount.textContent = `${apName} • DB: ${state.db.used}/${state.db.total} used (${state.db.unused} left)`;
  } else {
    els.packCount.textContent = apName;
  }

  const pid = state.puzzle?.id != null ? ` (id: ${state.puzzle.id})` : "";
  els.category.textContent = `Category: ${state.puzzle.category}${pid}`;
  els.usedLetters.textContent = iAmHost ? `Used: ${(state.used||[]).join(" ") || "—"}` : "";

  els.wedgeValue.textContent = wedgeLabel(state.current_wedge);

  const ap = state.players?.[state.active_idx];
  els.roundScore.textContent = String(ap?.round_bank ?? 0);
  els.prizeMini.textContent = (ap?.round_prizes?.length)
    ? `• Prizes: ${ap.round_prizes.map(x=>x.name||"PRIZE").join(", ")}`
    : "";

  renderPackDropdown();

  const slots = state.wheel_slots || [];
  const labels = slots.map(labelForSlot);
  drawWheel(labels, slots);

  if (typeof state.wheel_index === "number" && state.wheel_index !== prevWheelIndex) {
    spinToIndex(state.wheel_index, labels, slots);
  }

  renderBoard();
  renderPlayers();
  updateHostUI();
  updateTurnGating();
  renderFinalUI();
});

toast("Host: choose an active pack (or ALL). New Puzzle will pull from that pack. Save packs by name using the puzzle pack box.");
