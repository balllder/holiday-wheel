/* global io */
/**
 * TV Display for Holiday Wheel of Fortune
 * Optimized for AppleTV and large screens with keyboard navigation
 */

const ROOM = window.__ROOM__ || "main";
const socket = io({ transports: ["websocket", "polling"] });

const el = (id) => document.getElementById(id);

const els = {
  category: el("category"),
  board: el("vannaBoard"),
  phasePill: el("phasePill"),
  finalCountdown: el("finalCountdown"),
  wedgeValue: el("wedgeValue"),
  playersBar: el("playersBar"),
  controlsBar: el("controlsBar"),
  connDot: el("connDot"),
  connText: el("connText"),
  connStatus: el("connStatus"),
  wheel: el("wheel"),
  // Buttons
  spinBtn: el("spinBtn"),
  newPuzzleBtn: el("newPuzzleBtn"),
  startTossupBtn: el("startTossupBtn"),
  endTossupBtn: el("endTossupBtn"),
  startFinalBtn: el("startFinalBtn"),
  endFinalBtn: el("endFinalBtn"),
  newGameBtn: el("newGameBtn"),
  revealAllBtn: el("revealAllBtn"),
};

// Board layout (same as main app)
const BOARD_ROWS = 4;
const ROW_WIDTHS = [12, 14, 14, 12];
const ALPHA = /^[A-Z]$/;

// State
let state = null;
let controlsVisible = false;
let focusedBtnIdx = 0;
const navButtons = document.querySelectorAll("[data-nav]");

// ========== Connection Status ==========
function setConn(status) {
  els.connDot.classList.remove("on", "off", "warn");
  if (status === "on") {
    els.connDot.classList.add("on");
    els.connText.textContent = "Connected";
    els.connStatus.classList.add("connected");
  } else if (status === "warn") {
    els.connDot.classList.add("warn");
    els.connText.textContent = "Reconnecting...";
    els.connStatus.classList.remove("connected");
  } else {
    els.connDot.classList.add("off");
    els.connText.textContent = "Disconnected";
    els.connStatus.classList.remove("connected");
  }
}

// ========== Puzzle Board ==========
function wrapWordsToLines(answer) {
  const words = answer.trim().replace(/\s+/g, " ").split(" ").filter(Boolean);
  const lines = [];
  let cur = "";
  let lineIdx = 0;
  for (const w of words) {
    const maxW = ROW_WIDTHS[Math.min(lineIdx, BOARD_ROWS - 1)];
    if (!cur) {
      cur = w;
      continue;
    }
    if (cur.length + 1 + w.length <= maxW) cur = cur + " " + w;
    else {
      lines.push(cur);
      lineIdx++;
      cur = w;
    }
  }
  if (cur) lines.push(cur);
  while (lines.length > BOARD_ROWS) {
    const last = lines.pop();
    const maxW = ROW_WIDTHS[BOARD_ROWS - 1];
    lines[lines.length - 1] = (lines[lines.length - 1] + " " + last).slice(
      0,
      maxW
    );
  }
  while (lines.length < BOARD_ROWS) lines.push("");
  return lines.map((l, i) => {
    const maxW = ROW_WIDTHS[i];
    return l.length > maxW ? l.slice(0, maxW) : l;
  });
}

function layoutToGrid(answer) {
  const lines = wrapWordsToLines(answer);
  const grid = [];
  for (let r = 0; r < BOARD_ROWS; r++) {
    const rowWidth = ROW_WIDTHS[r];
    const line = lines[r];
    const row = Array.from({ length: rowWidth }, () => null);
    const padLeft = Math.max(0, Math.floor((rowWidth - line.length) / 2));
    for (let i = 0; i < line.length && padLeft + i < rowWidth; i++) {
      row[padLeft + i] = line[i];
    }
    grid.push(row);
  }
  return grid;
}

function renderBoard() {
  const ans = (state?.puzzle?.answer || "").toUpperCase();
  const grid = layoutToGrid(ans);
  const revealed = new Set(state?.revealed || []);
  els.board.innerHTML = "";

  for (let r = 0; r < BOARD_ROWS; r++) {
    const rowWidth = ROW_WIDTHS[r];
    const rowDiv = document.createElement("div");
    rowDiv.className = "tv-vRow";

    for (let c = 0; c < rowWidth; c++) {
      const v = grid[r][c];
      const cell = document.createElement("div");
      cell.className = "tv-vCell";

      if (v === null) {
        cell.classList.add("empty");
      } else if (v === " ") {
        cell.classList.add("space");
      } else if (ALPHA.test(v)) {
        if (revealed.has(v)) {
          cell.classList.add("revealed");
          cell.textContent = v;
        } else {
          cell.classList.add("hiddenTile");
        }
      } else {
        cell.classList.add("revealed");
        cell.textContent = v;
      }
      rowDiv.appendChild(cell);
    }
    els.board.appendChild(rowDiv);
  }
}

// ========== Wheel Drawing ==========
const ctx = els.wheel.getContext("2d");
let wheelAngle = 0;
let wheelAnim = null;

const WHEEL_COLORS = [
  "#c41e3a",
  "#0047ab",
  "#ff8c00",
  "#ffcc00",
  "#9932cc",
  "#ff1493",
  "#008b8b",
  "#dc143c",
  "#4169e1",
  "#ff4500",
  "#32cd32",
  "#9400d3",
  "#ff69b4",
  "#1e90ff",
  "#ffd700",
  "#00ced1",
  "#ff6347",
  "#8a2be2",
  "#00fa9a",
  "#ff7f50",
];

function shortPrizeName(name) {
  const s = String(name || "PRIZE").trim().toUpperCase();
  const parts = s.split(/\s+/).filter(Boolean);
  if (parts.length <= 2) return parts.join(" ");
  if (s.includes("GIFT") && s.includes("CARD")) return "GIFT CARD";
  return `${parts[0]} ${parts[1][0]}.`;
}

function labelForSlot(w) {
  if (typeof w === "number") return `$${w}`;
  if (typeof w === "string") return w;
  if (typeof w === "object" && w.type === "PRIZE") return shortPrizeName(w.name);
  return String(w);
}

function wedgeLabel(w) {
  if (w == null) return "--";
  if (typeof w === "number") return `$${w}`;
  if (typeof w === "string") return w;
  if (typeof w === "object" && w.type === "PRIZE") return `PRIZE: ${w.name}`;
  return String(w);
}

function getWedgeColor(slot, index) {
  if (slot === "BANKRUPT") return "#000000";
  if (slot === "LOSE A TURN") return "#ffffff";
  if (slot === "FREE PLAY") return "#39ff14";
  if (typeof slot === "object" && slot?.type === "PRIZE") return "#c0c0c0";
  return WHEEL_COLORS[index % WHEEL_COLORS.length];
}

function getTextColor(slot) {
  if (slot === "BANKRUPT") return "#c0c0c0";
  if (slot === "LOSE A TURN") return "#000000";
  if (slot === "FREE PLAY") return "#003300";
  if (typeof slot === "object" && slot?.type === "PRIZE") return "#333333";
  return "#ffffff";
}

function drawWheel(labels, slots) {
  const n = labels.length || 1;
  const arc = (Math.PI * 2) / n;
  const cx = els.wheel.width / 2,
    cy = els.wheel.height / 2;
  const radius = Math.min(cx, cy) - 6;
  const fontSize = Math.max(10, Math.floor(els.wheel.width / 26));

  ctx.clearRect(0, 0, els.wheel.width, els.wheel.height);

  for (let i = 0; i < n; i++) {
    const start = wheelAngle + i * arc;
    const end = start + arc;
    const slot = slots ? slots[i] : null;

    ctx.beginPath();
    ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, radius, start, end);
    ctx.closePath();
    ctx.fillStyle = getWedgeColor(slot, i);
    ctx.fill();
    ctx.strokeStyle = "rgba(0,0,0,.3)";
    ctx.lineWidth = 2;
    ctx.stroke();

    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(start + arc / 2);
    ctx.textAlign = "right";
    ctx.fillStyle = getTextColor(slot);
    ctx.font = `bold ${fontSize}px system-ui`;
    ctx.shadowColor = "rgba(0,0,0,.5)";
    ctx.shadowBlur = 2;
    ctx.fillText(String(labels[i]), radius - 12, 5);
    ctx.restore();
  }
}

function spinToIndex(targetIndex, labels, slots) {
  const n = labels.length;
  if (!n) return;

  const arc = (Math.PI * 2) / n;
  const desiredWheelAngle = -Math.PI / 2 - targetIndex * arc - arc / 2;
  const extraSpins = Math.PI * 2 * (3 + Math.floor(Math.random() * 3));
  const start = wheelAngle;
  const target = desiredWheelAngle - extraSpins;

  const duration = 1100;
  const t0 = performance.now();
  if (wheelAnim) cancelAnimationFrame(wheelAnim);

  function step(now) {
    const t = Math.min(1, (now - t0) / duration);
    const ease = 1 - Math.pow(1 - t, 3);
    wheelAngle = start + (target - start) * ease;
    drawWheel(labels, slots);
    if (t < 1) wheelAnim = requestAnimationFrame(step);
  }
  wheelAnim = requestAnimationFrame(step);
}

// ========== Players ==========
function renderPlayers() {
  const players = state?.players || [];
  const activeIdx = state?.active_idx;

  els.playersBar.innerHTML = players
    .map((p, i) => {
      const active = i === activeIdx ? "active" : "";
      const total = p.total || 0;
      const roundBank = p.round_bank || 0;
      return `
      <div class="tv-player ${active}">
        <div class="tv-player-name">${p.name}</div>
        <div class="tv-player-score">$${total.toLocaleString()}</div>
        <div class="tv-player-round">Round: $${roundBank.toLocaleString()}</div>
      </div>
    `;
    })
    .join("");
}

// ========== State Update ==========
function updateUI() {
  if (!state) return;

  // Category
  els.category.textContent = state.puzzle?.category || "--";

  // Phase pill
  const phase = state.phase || "normal";
  els.phasePill.textContent = phase.toUpperCase();
  els.phasePill.className = `tv-phase-pill ${phase}`;

  // Final countdown
  if (phase === "final" && state.final?.remaining_seconds != null) {
    els.finalCountdown.textContent = state.final.remaining_seconds;
    els.finalCountdown.classList.remove("hidden");
  } else {
    els.finalCountdown.classList.add("hidden");
  }

  // Current wedge
  els.wedgeValue.textContent = wedgeLabel(state.current_wedge);

  // Board
  renderBoard();

  // Players
  renderPlayers();

  // Wheel
  if (state.wheel_slots) {
    const labels = state.wheel_slots.map(labelForSlot);
    if (state.wheel_index != null) {
      spinToIndex(state.wheel_index, labels, state.wheel_slots);
    } else {
      drawWheel(labels, state.wheel_slots);
    }
  }
}

// ========== Keyboard Navigation (AppleTV Remote) ==========
function updateFocus() {
  navButtons.forEach((btn, i) => {
    btn.classList.toggle("focused", i === focusedBtnIdx);
  });
}

function toggleControls() {
  controlsVisible = !controlsVisible;
  els.controlsBar.classList.toggle("visible", controlsVisible);
  if (controlsVisible) {
    updateFocus();
  }
}

function handleKeydown(e) {
  // Menu button (or Escape) toggles controls
  if (e.key === "Escape" || e.key === "GoBack") {
    e.preventDefault();
    toggleControls();
    return;
  }

  if (!controlsVisible) {
    // Any key shows controls
    if (["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown", "Enter", " "].includes(e.key)) {
      e.preventDefault();
      toggleControls();
    }
    return;
  }

  // Navigate controls
  if (e.key === "ArrowLeft") {
    e.preventDefault();
    focusedBtnIdx = Math.max(0, focusedBtnIdx - 1);
    updateFocus();
  } else if (e.key === "ArrowRight") {
    e.preventDefault();
    focusedBtnIdx = Math.min(navButtons.length - 1, focusedBtnIdx + 1);
    updateFocus();
  } else if (e.key === "Enter" || e.key === " ") {
    e.preventDefault();
    const btn = navButtons[focusedBtnIdx];
    if (btn) btn.click();
  }
}

document.addEventListener("keydown", handleKeydown);

// ========== Button Handlers ==========
els.spinBtn?.addEventListener("click", () => {
  socket.emit("spin", { room: ROOM });
});

els.newPuzzleBtn?.addEventListener("click", () => {
  socket.emit("new_puzzle", { room: ROOM });
});

els.startTossupBtn?.addEventListener("click", () => {
  socket.emit("start_tossup", { room: ROOM });
});

els.endTossupBtn?.addEventListener("click", () => {
  socket.emit("end_tossup", { room: ROOM });
});

els.startFinalBtn?.addEventListener("click", () => {
  socket.emit("start_final", { room: ROOM });
});

els.endFinalBtn?.addEventListener("click", () => {
  socket.emit("end_final", { room: ROOM });
});

els.newGameBtn?.addEventListener("click", () => {
  socket.emit("new_game", { room: ROOM });
});

els.revealAllBtn?.addEventListener("click", () => {
  // Reveal all letters (useful for showing answer)
  socket.emit("reveal_all", { room: ROOM });
});

// ========== Socket Events ==========
socket.on("connect", () => {
  setConn("on");
  socket.emit("join", { room: ROOM });
});

socket.on("disconnect", () => {
  setConn("off");
});

socket.on("connect_error", () => {
  setConn("warn");
});

socket.on("state", (data) => {
  state = data;
  updateUI();
});

socket.on("toast", (data) => {
  // Could show toast notification on TV
  console.log("Toast:", data.msg);
});

// Initialize wheel
drawWheel(["..."]);
