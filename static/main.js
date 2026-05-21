const elements = {
  roomInput: document.getElementById("roomInput"),
  nameInput: document.getElementById("nameInput"),
  joinButton: document.getElementById("joinButton"),
  joinPanel: document.getElementById("joinPanel"),
  gamePanel: document.getElementById("gamePanel"),
  roomLabel: document.getElementById("roomLabel"),
  phaseSummary: document.getElementById("phaseSummary"),
  playersList: document.getElementById("playersList"),
  primaryAction: document.getElementById("primaryAction"),
  privatePanel: document.getElementById("privatePanel"),
  voiceState: document.getElementById("voiceState"),
  publicTimeline: document.getElementById("publicTimeline"),
  messageLog: document.getElementById("messageLog"),
  statusText: document.getElementById("statusText"),
};

const appState = {
  roomId: "",
  sessionToken: "",
  playerId: "",
  snapshot: null,
  socket: null,
};

const phaseLabels = {
  LOBBY: "大厅等待",
  TEAM_PROPOSAL: "队长组队",
  TEAM_VOTE: "组队投票",
  MISSION_VOTE: "任务投票",
  MISSION_RESULT_DISCUSSION: "任务结果讨论",
  ASSASSINATION: "刺杀阶段",
  GAME_OVER: "游戏结束",
};

elements.joinButton.addEventListener("click", joinRoom);
elements.roomInput.addEventListener("keydown", submitOnEnter);
elements.nameInput.addEventListener("keydown", submitOnEnter);

function submitOnEnter(event) {
  if (event.key === "Enter") {
    joinRoom();
  }
}

async function joinRoom() {
  const roomId = elements.roomInput.value.trim();
  const nickname = elements.nameInput.value.trim();
  if (!roomId || !nickname) {
    setStatus("请填写房间号和昵称。", true);
    return;
  }

  elements.joinButton.disabled = true;
  setStatus("正在加入房间...");
  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/join`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nickname}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "加入房间失败。");
    }

    appState.roomId = payload.room_id || roomId;
    appState.sessionToken = payload.session_token;
    appState.playerId = payload.player_id;
    appState.snapshot = payload.snapshot;

    elements.joinPanel.hidden = true;
    elements.gamePanel.hidden = false;
    renderSnapshot(payload.snapshot);
    addMessage("已加入房间。");
    connectWebSocket();
  } catch (error) {
    setStatus(error.message || "加入房间失败。", true);
  } finally {
    elements.joinButton.disabled = false;
  }
}

function connectWebSocket() {
  if (appState.socket) {
    appState.socket.close();
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/${encodeURIComponent(appState.roomId)}`);
  appState.socket = socket;

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({type: "hello", session_token: appState.sessionToken}));
    addMessage("实时连接已建立。");
  });

  socket.addEventListener("message", (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch {
      addMessage("收到无法解析的实时消息。", true);
      return;
    }

    if (payload.type === "state") {
      appState.snapshot = payload.snapshot;
      renderSnapshot(payload.snapshot);
      return;
    }
    if (payload.type === "error") {
      addMessage(payload.message || "服务端返回错误。", true);
      renderPrimaryAction(appState.snapshot);
      return;
    }
    if (payload.type === "pong") {
      addMessage("连接心跳正常。");
    }
  });

  socket.addEventListener("close", () => {
    addMessage("实时连接已断开，刷新页面可重新加入。", true);
  });

  socket.addEventListener("error", () => {
    addMessage("实时连接异常。", true);
  });
}

function renderSnapshot(snapshot) {
  if (!snapshot) {
    return;
  }
  elements.roomLabel.textContent = snapshot.room?.room_id || appState.roomId || "未知房间";
  renderPhase(snapshot);
  renderPlayers(snapshot);
  renderPrivatePanel(snapshot.private_panel);
  renderVoiceState(snapshot.voice_state);
  renderTimeline(snapshot.public_timeline || snapshot.publicTimeline || []);
  renderPrimaryAction(snapshot);
}

function renderPhase(snapshot) {
  const phase = snapshot.phase_summary?.phase || "UNKNOWN";
  const label = phaseLabels[phase] || phase;
  const parts = [label];
  if (snapshot.phase_summary?.round_number) {
    parts.push(`第 ${snapshot.phase_summary.round_number} 轮`);
  }
  if (typeof snapshot.phase_summary?.score_good === "number" && typeof snapshot.phase_summary?.score_evil === "number") {
    parts.push(`好人 ${snapshot.phase_summary.score_good} : 邪恶 ${snapshot.phase_summary.score_evil}`);
  }
  if (snapshot.phase_summary?.required_team_size) {
    parts.push(`本轮队伍 ${snapshot.phase_summary.required_team_size} 人`);
  }
  if (snapshot.phase_summary?.winner) {
    parts.push(`胜利方：${snapshot.phase_summary.winner}`);
  }
  elements.phaseSummary.textContent = parts.join(" · ");
}

function renderPlayers(snapshot) {
  const players = normalizePlayers(snapshot);
  elements.playersList.replaceChildren();
  if (players.length === 0) {
    const empty = document.createElement("li");
    empty.className = "empty-state";
    empty.textContent = "暂无玩家。";
    elements.playersList.append(empty);
    return;
  }

  players.forEach((player) => {
    const item = document.createElement("li");
    const title = document.createElement("span");
    const meta = document.createElement("span");
    title.className = "player-title";
    meta.className = "player-meta";
    title.textContent = player.display || player.nickname || player.player_id || "未知玩家";
    meta.textContent = playerBadges(player).join(" · ");
    item.append(title, meta);
    elements.playersList.append(item);
  });
}

function normalizePlayers(snapshot) {
  if (Array.isArray(snapshot.participants)) {
    return snapshot.participants.map((participant) => ({
      player_id: participant.player_id,
      seat: participant.seat,
      nickname: participant.nickname,
      display: `${participant.seat || "?"}号-${participant.nickname || "玩家"}`,
      is_host: Boolean(participant.is_host),
      is_leader: participant.player_id === snapshot.phase_summary?.leader_id,
      ready: Boolean(participant.ready),
    }));
  }

  if (Array.isArray(snapshot.players)) {
    return snapshot.players.map((player, index) => ({
      player_id: player.player_id,
      seat: index + 1,
      display: player.display,
      is_host: player.player_id === snapshot.room?.host_id,
      is_leader: Boolean(player.is_leader) || player.player_id === snapshot.phase_summary?.leader_id,
      ready: undefined,
    }));
  }

  return [];
}

function playerBadges(player) {
  const badges = [`${player.seat || "?"}号`];
  if (player.is_host) {
    badges.push("房主");
  }
  if (player.is_leader) {
    badges.push("队长");
  }
  if (player.ready === true) {
    badges.push("已准备");
  } else if (player.ready === false) {
    badges.push("未准备");
  }
  return badges;
}

function renderPrivatePanel(privatePanel) {
  elements.privatePanel.replaceChildren();
  if (!privatePanel) {
    elements.privatePanel.textContent = "开局后显示你的身份。";
    return;
  }

  const role = document.createElement("p");
  role.textContent = `角色：${privatePanel.role || "未知"}`;
  const side = document.createElement("p");
  side.textContent = `阵营：${privatePanel.side || "未知"}`;
  elements.privatePanel.append(role, side);

  const visiblePlayers = Array.isArray(privatePanel.visible_players) ? privatePanel.visible_players : [];
  const visibleTitle = document.createElement("p");
  visibleTitle.textContent = visiblePlayers.length > 0 ? "你可见的玩家：" : "当前没有额外可见玩家。";
  elements.privatePanel.append(visibleTitle);

  if (visiblePlayers.length > 0) {
    const list = document.createElement("ul");
    visiblePlayers.forEach((player) => {
      const item = document.createElement("li");
      item.textContent = player.display || player.player_id || "未知玩家";
      list.append(item);
    });
    elements.privatePanel.append(list);
  }
}

function renderVoiceState(voiceState) {
  if (!voiceState) {
    elements.voiceState.textContent = "大厅阶段暂未开放语音状态。";
    return;
  }
  const policy = voiceState.publish_policy || "unknown";
  elements.voiceState.textContent = voiceState.can_publish_audio
    ? `当前可发言，策略：${policy}`
    : `当前静音，策略：${policy}`;
}

function renderTimeline(timeline) {
  elements.publicTimeline.replaceChildren();
  if (!Array.isArray(timeline) || timeline.length === 0) {
    const item = document.createElement("li");
    item.className = "empty-state";
    item.textContent = "暂无公开事件。";
    elements.publicTimeline.append(item);
    return;
  }

  timeline.forEach((event) => {
    const item = document.createElement("li");
    item.textContent = event.summary || event.event_type || String(event);
    elements.publicTimeline.append(item);
  });
}

function renderPrimaryAction(snapshot) {
  elements.primaryAction.replaceChildren();
  if (!snapshot) {
    elements.primaryAction.textContent = "等待房间状态。";
    return;
  }

  const isLobby = snapshot.phase_summary?.phase === "LOBBY";
  const you = snapshot.you || {};
  const controls = document.createElement("div");
  controls.className = "action-controls";

  if (isLobby) {
    const readyButton = document.createElement("button");
    readyButton.type = "button";
    readyButton.textContent = you.ready ? "取消准备" : "准备";
    readyButton.addEventListener("click", () => sendCommand({type: "ready", ready: !Boolean(you.ready)}));
    controls.append(readyButton);

    const playerCount = snapshot.room?.player_count || snapshot.participants?.length || 0;
    if (you.is_host && playerCount >= 5) {
      const startButton = document.createElement("button");
      startButton.type = "button";
      startButton.textContent = "开始游戏";
      startButton.addEventListener("click", () => sendCommand({type: "start_game"}));
      controls.append(startButton);
    }

    if (you.is_host) {
      controls.append(makeResetButton());
    }

    const hint = document.createElement("p");
    hint.className = "muted";
    hint.textContent = you.is_host && playerCount < 5 ? "至少 5 人后房主可开始游戏。" : "等待玩家准备或房主开局。";
    elements.primaryAction.append(controls, hint);
    return;
  }

  const actionType = snapshot.my_action?.type || "wait";
  const text = document.createElement("p");
  if (["select_team", "team_vote", "mission_vote", "assassinate"].includes(actionType)) {
    text.textContent = "该阶段操作将在后续版本接入。";
  } else {
    text.textContent = "当前阶段暂无需要你提交的操作。";
  }
  elements.primaryAction.append(text);

  if (you.is_host) {
    const hostControls = document.createElement("div");
    hostControls.className = "action-controls";
    hostControls.append(makeResetButton());
    elements.primaryAction.append(hostControls);
  }
}

function makeResetButton() {
  const resetButton = document.createElement("button");
  resetButton.type = "button";
  resetButton.className = "secondary-button";
  resetButton.textContent = "重置房间";
  resetButton.addEventListener("click", () => sendCommand({type: "reset"}));
  return resetButton;
}

async function sendCommand(command) {
  if (!appState.sessionToken || !appState.roomId) {
    addMessage("请先加入房间。", true);
    return;
  }

  const message = {
    type: "command",
    request_id: makeRequestId(),
    command,
  };

  if (appState.socket?.readyState === WebSocket.OPEN) {
    appState.socket.send(JSON.stringify(message));
    return;
  }

  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(appState.roomId)}/command`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        session_token: appState.sessionToken,
        request_id: message.request_id,
        command,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.detail || "操作失败。");
    }
    appState.snapshot = payload.snapshot;
    renderSnapshot(payload.snapshot);
  } catch (error) {
    addMessage(error.message || "操作失败。", true);
  }
}

function makeRequestId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID().slice(0, 64);
  }
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function setStatus(message, isError = false) {
  elements.statusText.textContent = message;
  elements.statusText.classList.toggle("error-text", isError);
}

function addMessage(message, isError = false) {
  const item = document.createElement("p");
  item.textContent = message;
  item.className = isError ? "error-text" : "";
  elements.messageLog.append(item);
}
