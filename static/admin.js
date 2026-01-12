/**
 * Admin page JavaScript for Holiday Wheel
 */

(function() {
  "use strict";

  // Elements - Host Auth
  const hostCodeInput = document.getElementById("hostCode");
  const claimHostBtn = document.getElementById("claimHostBtn");
  const hostStatus = document.getElementById("hostStatus");
  const logoutBtn = document.getElementById("logoutBtn");

  // Elements - User Management
  const userMgmtSection = document.getElementById("userMgmtSection");
  const refreshUsersBtn = document.getElementById("refreshUsersBtn");
  const usersBody = document.getElementById("usersBody");
  const totalUsers = document.getElementById("totalUsers");
  const verifiedUsers = document.getElementById("verifiedUsers");
  const unverifiedUsers = document.getElementById("unverifiedUsers");

  // Elements - Room Management
  const roomMgmtSection = document.getElementById("roomMgmtSection");
  const refreshRoomsBtn = document.getElementById("refreshRoomsBtn");
  const roomsBody = document.getElementById("roomsBody");

  // Elements - Room Player Management
  const roomPlayerMgmt = document.getElementById("roomPlayerMgmt");
  const selectedRoomName = document.getElementById("selectedRoomName");
  const closeRoomMgmt = document.getElementById("closeRoomMgmt");
  const addPlayerSelect = document.getElementById("addPlayerSelect");
  const addPlayerBtn = document.getElementById("addPlayerBtn");
  const deleteRoomBtn = document.getElementById("deleteRoomBtn");
  const roomPlayersBody = document.getElementById("roomPlayersBody");

  let selectedRoom = null;

  // Elements - Pack Management
  const packMgmtSection = document.getElementById("packMgmtSection");
  const refreshPacksBtn = document.getElementById("refreshPacksBtn");
  const packsBody = document.getElementById("packsBody");
  const newPackName = document.getElementById("newPackName");
  const newPackPuzzles = document.getElementById("newPackPuzzles");
  const createPackBtn = document.getElementById("createPackBtn");
  const packFile = document.getElementById("packFile");
  const importPackBtn = document.getElementById("importPackBtn");

  // Elements - Room Config
  const configSection = document.getElementById("configSection");
  const configRoom = document.getElementById("configRoom");
  const loadConfigBtn = document.getElementById("loadConfigBtn");
  const cfgVowelCost = document.getElementById("cfgVowelCost");
  const cfgFinalSeconds = document.getElementById("cfgFinalSeconds");
  const cfgFinalJackpot = document.getElementById("cfgFinalJackpot");
  const cfgPrizeCash = document.getElementById("cfgPrizeCash");
  const cfgActivePack = document.getElementById("cfgActivePack");
  const saveConfigBtn = document.getElementById("saveConfigBtn");

  let isHost = false;

  // Format timestamp to readable date
  function formatDate(timestamp) {
    if (!timestamp) return "-";
    const date = new Date(timestamp * 1000);
    return date.toLocaleDateString() + " " + date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // Show status message
  function showStatus(message, isError = false) {
    hostStatus.textContent = message;
    hostStatus.className = "adminStatus " + (isError ? "error" : "success");
    hostStatus.classList.remove("hidden");
  }

  // Update UI based on host status
  function updateHostUI() {
    if (isHost) {
      claimHostBtn.textContent = "Authenticated";
      claimHostBtn.disabled = true;
      hostCodeInput.disabled = true;
      userMgmtSection.classList.remove("locked");
      roomMgmtSection.classList.remove("locked");
      packMgmtSection.classList.remove("locked");
      configSection.classList.remove("locked");
      loadUsers();
      loadRooms();
      loadPacks();
      loadConfig();
    } else {
      claimHostBtn.textContent = "Authenticate";
      claimHostBtn.disabled = false;
      hostCodeInput.disabled = false;
      userMgmtSection.classList.add("locked");
      roomMgmtSection.classList.add("locked");
      packMgmtSection.classList.add("locked");
      configSection.classList.add("locked");
    }
  }

  // Verify host code
  async function verifyHost() {
    const code = hostCodeInput.value.trim();
    if (!code) {
      showStatus("Please enter the host code", true);
      return;
    }

    try {
      const response = await fetch("/auth/admin/verify-host", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code })
      });

      const data = await response.json();
      if (data.ok) {
        isHost = true;
        showStatus("Host access granted");
        updateHostUI();
      } else {
        showStatus(data.error || "Invalid host code", true);
      }
    } catch (err) {
      showStatus("Failed to verify host code", true);
      console.error(err);
    }
  }

  // Load users list
  async function loadUsers() {
    if (!isHost) return;

    usersBody.innerHTML = '<tr><td colspan="6" class="muted">Loading...</td></tr>';

    try {
      const response = await fetch("/auth/admin/users");
      const data = await response.json();

      if (!data.ok) {
        if (response.status === 403) {
          isHost = false;
          updateHostUI();
          showStatus("Host session expired. Please re-authenticate.", true);
        }
        usersBody.innerHTML = '<tr><td colspan="6" class="muted error">Failed to load users</td></tr>';
        return;
      }

      // Update stats
      if (data.stats) {
        totalUsers.textContent = data.stats.total || 0;
        verifiedUsers.textContent = data.stats.verified || 0;
        unverifiedUsers.textContent = data.stats.unverified || 0;
      }

      // Render users table
      if (!data.users || data.users.length === 0) {
        usersBody.innerHTML = '<tr><td colspan="6" class="muted">No users found</td></tr>';
        return;
      }

      usersBody.innerHTML = data.users.map(user => `
        <tr data-user-id="${user.id}">
          <td>${user.id}</td>
          <td>${escapeHtml(user.email)}</td>
          <td>${escapeHtml(user.display_name)}</td>
          <td>${user.verified ? '<span class="badge success">Yes</span>' : '<span class="badge warning">No</span>'}</td>
          <td>${formatDate(user.created_at)}</td>
          <td class="actions">
            ${!user.verified ? `
              <button class="small secondary" onclick="adminVerifyUser(${user.id})">Verify</button>
              <button class="small secondary" onclick="adminResendEmail(${user.id})">Resend</button>
            ` : ""}
            <button class="small danger" onclick="adminDeleteUser(${user.id}, '${escapeHtml(user.email)}')">Delete</button>
          </td>
        </tr>
      `).join("");

    } catch (err) {
      usersBody.innerHTML = '<tr><td colspan="6" class="muted error">Failed to load users</td></tr>';
      console.error(err);
    }
  }

  // Load rooms list
  async function loadRooms() {
    if (!isHost) return;

    roomsBody.innerHTML = '<tr><td colspan="4" class="muted">Loading...</td></tr>';

    try {
      const response = await fetch("/auth/admin/rooms");
      const data = await response.json();

      if (!data.ok) {
        roomsBody.innerHTML = '<tr><td colspan="4" class="muted error">Failed to load rooms</td></tr>';
        return;
      }

      if (!data.rooms || data.rooms.length === 0) {
        roomsBody.innerHTML = '<tr><td colspan="4" class="muted">No active rooms</td></tr>';
        return;
      }

      roomsBody.innerHTML = data.rooms.map(room => `
        <tr>
          <td>${escapeHtml(room.name)}</td>
          <td>${room.player_count || 0} / ${room.total_slots || 0}</td>
          <td>${formatDate(room.last_activity_at)}</td>
          <td class="actions">
            <button class="small secondary" onclick="openRoomPlayerMgmt('${escapeHtml(room.name)}')">Manage</button>
            <a href="/?room=${encodeURIComponent(room.name)}" class="button small secondary">Join</a>
          </td>
        </tr>
      `).join("");

    } catch (err) {
      roomsBody.innerHTML = '<tr><td colspan="4" class="muted error">Failed to load rooms</td></tr>';
      console.error(err);
    }
  }

  // Open room player management panel
  window.openRoomPlayerMgmt = function(roomName) {
    selectedRoom = roomName;
    selectedRoomName.textContent = roomName;
    roomPlayerMgmt.classList.remove("hidden");
    loadRoomPlayers();
    loadAvailableUsers();
  };

  // Close room player management panel
  function closeRoomPlayerMgmt() {
    selectedRoom = null;
    roomPlayerMgmt.classList.add("hidden");
    roomPlayersBody.innerHTML = '<tr><td colspan="6" class="muted">Select a room to manage</td></tr>';
    addPlayerSelect.innerHTML = '<option value="">Select user to add...</option>';
  }

  // Load players in the selected room
  async function loadRoomPlayers() {
    if (!selectedRoom) return;

    roomPlayersBody.innerHTML = '<tr><td colspan="6" class="muted">Loading...</td></tr>';

    try {
      const response = await fetch(`/auth/admin/rooms/${encodeURIComponent(selectedRoom)}/players`);
      const data = await response.json();

      if (!data.ok) {
        roomPlayersBody.innerHTML = '<tr><td colspan="6" class="muted error">Failed to load players</td></tr>';
        return;
      }

      if (!data.players || data.players.length === 0) {
        roomPlayersBody.innerHTML = '<tr><td colspan="6" class="muted">No players in this room</td></tr>';
        return;
      }

      roomPlayersBody.innerHTML = data.players.map(p => `
        <tr>
          <td>${p.idx + 1}</td>
          <td>${escapeHtml(p.name)}</td>
          <td>${escapeHtml(p.email || '-')}</td>
          <td>${p.connected ? '<span class="badge success">Yes</span>' : '<span class="badge warning">No</span>'}</td>
          <td>$${p.total || 0}</td>
          <td class="actions">
            <button class="small danger" onclick="adminRemovePlayer(${p.idx})">Remove</button>
          </td>
        </tr>
      `).join("");

    } catch (err) {
      roomPlayersBody.innerHTML = '<tr><td colspan="6" class="muted error">Failed to load players</td></tr>';
      console.error(err);
    }
  }

  // Load users available to add to the room
  async function loadAvailableUsers() {
    if (!selectedRoom) return;

    addPlayerSelect.innerHTML = '<option value="">Loading...</option>';

    try {
      const response = await fetch(`/auth/admin/users/available/${encodeURIComponent(selectedRoom)}`);
      const data = await response.json();

      addPlayerSelect.innerHTML = '<option value="">Select user to add...</option>';

      if (data.ok && data.users && data.users.length > 0) {
        data.users.forEach(user => {
          const opt = document.createElement("option");
          opt.value = user.id;
          opt.textContent = `${user.display_name} (${user.email})`;
          addPlayerSelect.appendChild(opt);
        });
      }
    } catch (err) {
      addPlayerSelect.innerHTML = '<option value="">Failed to load users</option>';
      console.error(err);
    }
  }

  // Add a user as player to the room
  async function addPlayerToRoom() {
    if (!selectedRoom) return;

    const userId = addPlayerSelect.value;
    if (!userId) {
      alert("Please select a user to add");
      return;
    }

    try {
      const response = await fetch(`/auth/admin/rooms/${encodeURIComponent(selectedRoom)}/players`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ user_id: parseInt(userId) })
      });

      const data = await response.json();
      if (data.ok) {
        loadRoomPlayers();
        loadAvailableUsers();
        loadRooms();
      } else {
        alert(data.error || "Failed to add player");
      }
    } catch (err) {
      alert("Failed to add player");
      console.error(err);
    }
  }

  // Remove a player from the room
  window.adminRemovePlayer = async function(playerIdx) {
    if (!selectedRoom) return;

    if (!confirm("Are you sure you want to remove this player from the room?")) {
      return;
    }

    try {
      const response = await fetch(`/auth/admin/rooms/${encodeURIComponent(selectedRoom)}/players/${playerIdx}`, {
        method: "DELETE"
      });

      const data = await response.json();
      if (data.ok) {
        loadRoomPlayers();
        loadAvailableUsers();
        loadRooms();
      } else {
        alert(data.error || "Failed to remove player");
      }
    } catch (err) {
      alert("Failed to remove player");
      console.error(err);
    }
  };

  // Delete the entire room
  async function deleteRoom() {
    if (!selectedRoom) return;

    if (!confirm(`Are you sure you want to delete room "${selectedRoom}"? This will remove all players and game data. This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`/auth/admin/rooms/${encodeURIComponent(selectedRoom)}`, {
        method: "DELETE"
      });

      const data = await response.json();
      if (data.ok) {
        closeRoomPlayerMgmt();
        loadRooms();
      } else {
        alert(data.error || "Failed to delete room");
      }
    } catch (err) {
      alert("Failed to delete room");
      console.error(err);
    }
  }

  // Load packs list
  async function loadPacks() {
    if (!isHost) return;

    packsBody.innerHTML = '<tr><td colspan="4" class="muted">Loading...</td></tr>';

    try {
      const response = await fetch("/auth/admin/packs");
      const data = await response.json();

      if (!data.ok) {
        packsBody.innerHTML = '<tr><td colspan="4" class="muted error">Failed to load packs</td></tr>';
        return;
      }

      // Also update the pack selector in config
      cfgActivePack.innerHTML = '<option value="">All Packs (no filter)</option>';
      if (data.packs && data.packs.length > 0) {
        data.packs.forEach(pack => {
          const opt = document.createElement("option");
          opt.value = pack.id;
          opt.textContent = `${pack.name} (${pack.puzzle_count} puzzles)`;
          cfgActivePack.appendChild(opt);
        });
      }

      if (!data.packs || data.packs.length === 0) {
        packsBody.innerHTML = '<tr><td colspan="4" class="muted">No packs found</td></tr>';
        return;
      }

      packsBody.innerHTML = data.packs.map(pack => `
        <tr>
          <td>${pack.id}</td>
          <td>${escapeHtml(pack.name)}</td>
          <td>${pack.puzzle_count}</td>
          <td class="actions">
            <button class="small danger" onclick="adminDeletePack(${pack.id}, '${escapeHtml(pack.name)}')">Delete</button>
          </td>
        </tr>
      `).join("");

    } catch (err) {
      packsBody.innerHTML = '<tr><td colspan="4" class="muted error">Failed to load packs</td></tr>';
      console.error(err);
    }
  }

  // Load room config
  async function loadConfig() {
    if (!isHost) return;

    const room = configRoom.value.trim() || "main";

    try {
      const response = await fetch(`/auth/admin/config/${encodeURIComponent(room)}`);
      const data = await response.json();

      if (!data.ok) {
        alert(data.error || "Failed to load config");
        return;
      }

      const cfg = data.config;
      cfgVowelCost.value = cfg.vowel_cost || "";
      cfgFinalSeconds.value = cfg.final_seconds || "";
      cfgFinalJackpot.value = cfg.final_jackpot || "";
      cfgPrizeCash.value = cfg.prize_replace_cash_csv || "";
      cfgActivePack.value = cfg.active_pack_id || "";

    } catch (err) {
      console.error(err);
      alert("Failed to load config");
    }
  }

  // Save room config
  async function saveConfig() {
    if (!isHost) return;

    const room = configRoom.value.trim() || "main";

    try {
      const response = await fetch(`/auth/admin/config/${encodeURIComponent(room)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          vowel_cost: cfgVowelCost.value || null,
          final_seconds: cfgFinalSeconds.value || null,
          final_jackpot: cfgFinalJackpot.value || null,
          prize_cash_csv: cfgPrizeCash.value || null,
          active_pack_id: cfgActivePack.value || null
        })
      });

      const data = await response.json();
      if (data.ok) {
        alert(data.message || "Configuration saved");
      } else {
        alert(data.error || "Failed to save config");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to save config");
    }
  }

  // Create new pack
  async function createPack() {
    if (!isHost) return;

    const name = newPackName.value.trim();
    const puzzles = newPackPuzzles.value.trim();

    if (!name) {
      alert("Please enter a pack name");
      return;
    }
    if (!puzzles) {
      alert("Please enter some puzzles");
      return;
    }

    try {
      const response = await fetch("/auth/admin/packs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, puzzles })
      });

      const data = await response.json();
      if (data.ok) {
        alert(data.message || "Pack created");
        newPackName.value = "";
        newPackPuzzles.value = "";
        loadPacks();
      } else {
        alert(data.error || "Failed to create pack");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to create pack");
    }
  }

  // Import packs from JSON
  async function importPacks() {
    if (!isHost) return;

    const file = packFile.files[0];
    if (!file) {
      alert("Please select a JSON file");
      return;
    }

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/auth/admin/packs/import", {
        method: "POST",
        body: formData
      });

      const data = await response.json();
      if (data.ok) {
        let msg = `Imported ${data.total_added} puzzles`;
        if (data.packs && data.packs.length > 0) {
          msg += ":\n" + data.packs.map(p => `- ${p.name}: ${p.added} puzzles`).join("\n");
        }
        alert(msg);
        packFile.value = "";
        loadPacks();
      } else {
        alert(data.error || "Failed to import packs");
      }
    } catch (err) {
      console.error(err);
      alert("Failed to import packs");
    }
  }

  // Escape HTML to prevent XSS
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  // Delete user
  window.adminDeleteUser = async function(userId, email) {
    if (!confirm(`Are you sure you want to delete user "${email}"? This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`/auth/admin/users/${userId}`, {
        method: "DELETE"
      });
      const data = await response.json();

      if (data.ok) {
        loadUsers();
      } else {
        alert(data.error || "Failed to delete user");
      }
    } catch (err) {
      alert("Failed to delete user");
      console.error(err);
    }
  };

  // Manually verify user
  window.adminVerifyUser = async function(userId) {
    try {
      const response = await fetch(`/auth/admin/users/${userId}/verify`, {
        method: "POST"
      });
      const data = await response.json();

      if (data.ok) {
        loadUsers();
      } else {
        alert(data.error || "Failed to verify user");
      }
    } catch (err) {
      alert("Failed to verify user");
      console.error(err);
    }
  };

  // Resend verification email
  window.adminResendEmail = async function(userId) {
    try {
      const response = await fetch(`/auth/admin/users/${userId}/resend`, {
        method: "POST"
      });
      const data = await response.json();

      if (data.ok) {
        alert(data.message || "Verification email sent");
      } else {
        alert(data.error || "Failed to send email");
      }
    } catch (err) {
      alert("Failed to send email");
      console.error(err);
    }
  };

  // Delete pack
  window.adminDeletePack = async function(packId, name) {
    if (!confirm(`Are you sure you want to delete pack "${name}" and all its puzzles? This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`/auth/admin/packs/${packId}`, {
        method: "DELETE"
      });
      const data = await response.json();

      if (data.ok) {
        loadPacks();
      } else {
        alert(data.error || "Failed to delete pack");
      }
    } catch (err) {
      alert("Failed to delete pack");
      console.error(err);
    }
  };

  // Logout
  async function logout() {
    try {
      await fetch("/auth/logout", { method: "POST" });
      window.location.href = "/auth/login";
    } catch (err) {
      console.error(err);
      window.location.href = "/auth/login";
    }
  }

  // Event listeners
  claimHostBtn.addEventListener("click", verifyHost);
  hostCodeInput.addEventListener("keypress", (e) => {
    if (e.key === "Enter") verifyHost();
  });

  refreshUsersBtn.addEventListener("click", loadUsers);
  refreshRoomsBtn.addEventListener("click", loadRooms);
  refreshPacksBtn.addEventListener("click", loadPacks);
  loadConfigBtn.addEventListener("click", loadConfig);
  saveConfigBtn.addEventListener("click", saveConfig);
  createPackBtn.addEventListener("click", createPack);
  importPackBtn.addEventListener("click", importPacks);
  logoutBtn.addEventListener("click", logout);

  // Room player management events
  closeRoomMgmt.addEventListener("click", closeRoomPlayerMgmt);
  addPlayerBtn.addEventListener("click", addPlayerToRoom);
  deleteRoomBtn.addEventListener("click", deleteRoom);

  // Check if already authenticated as host (session may persist)
  async function checkHostStatus() {
    try {
      const response = await fetch("/auth/admin/users");
      if (response.ok) {
        isHost = true;
        showStatus("Host session restored");
        updateHostUI();
      }
    } catch (err) {
      // Not authenticated, that's fine
    }
  }

  // Initialize
  checkHostStatus();
})();
