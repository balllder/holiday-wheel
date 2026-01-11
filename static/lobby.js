/* Lobby page JavaScript */

const roomList = document.getElementById("roomList");
const customRoomInput = document.getElementById("customRoomInput");
const joinCustomBtn = document.getElementById("joinCustomBtn");
const refreshRoomsBtn = document.getElementById("refreshRoomsBtn");
const logoutBtn = document.getElementById("logoutBtn");

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function joinRoom(roomName) {
  window.location.href = "/?room=" + encodeURIComponent(roomName);
}

async function loadRooms() {
  roomList.innerHTML = '<div class="loading">Loading rooms...</div>';

  try {
    const res = await fetch("/auth/rooms");
    const data = await res.json();

    if (data.ok && data.rooms.length > 0) {
      roomList.innerHTML = data.rooms.map(room => `
        <div class="roomCard">
          <div class="roomInfo">
            <div class="roomName">${escapeHtml(room.name)}</div>
            <div class="roomPlayers muted small">${room.player_count}/${room.total_slots} players</div>
          </div>
          <button class="secondary" onclick="joinRoom('${escapeHtml(room.name).replace(/'/g, "\\'")}')">Join</button>
        </div>
      `).join("");
    } else {
      roomList.innerHTML = '<div class="muted">No active rooms. Enter a room name above to create one!</div>';
    }
  } catch (err) {
    roomList.innerHTML = '<div class="authError">Failed to load rooms. Please try again.</div>';
  }
}

joinCustomBtn.addEventListener("click", () => {
  const name = customRoomInput.value.trim();
  if (name) {
    joinRoom(name);
  } else {
    customRoomInput.focus();
  }
});

customRoomInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    joinCustomBtn.click();
  }
});

refreshRoomsBtn.addEventListener("click", loadRooms);

logoutBtn.addEventListener("click", async () => {
  await fetch("/auth/logout", { method: "POST" });
  window.location.href = "/auth/login";
});

// Initial load
loadRooms();
