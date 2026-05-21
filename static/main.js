const $ = (id) => document.getElementById(id);

const elements = {
  joinView: $("joinView"),
  gameView: $("gameView"),
  roomInput: $("roomInput"),
  nameInput: $("nameInput"),
  joinBtn: $("joinBtn"),
  lastRoomCard: $("lastRoomCard"),
  lastRoomName: $("lastRoomName"),
  roomCode: $("roomCode"),
  phaseTitle: $("phaseTitle"),
  scoreText: $("scoreText"),
  resetBtn: $("resetBtn"),
  backBtn: $("backBtn"),
  copyRoomBtn: $("copyRoomBtn"),
  voiceBtn: $("voiceBtn"),
  listenBtn: $("listenBtn"),
  oddPlayersList: $("oddPlayersList"),
  evenPlayersList: $("evenPlayersList"),
  playerCountText: $("playerCountText"),
  announcementText: $("announcementText"),
  errorBox: $("errorBox"),
  actionPanel: $("actionPanel"),
  permissionText: $("permissionText"),
  actionArea: $("actionArea"),
  chatStatusText: $("chatStatusText"),
  chatMessages: $("chatMessages"),
  chatInput: $("chatInput"),
  sendChatBtn: $("sendChatBtn"),
  identityHint: $("identityHint"),
  phaseToast: $("phaseToast"),
  modalBackdrop: $("modalBackdrop"),
  roleModal: $("roleModal"),
  roleModalBody: $("roleModalBody"),
  infoModal: $("infoModal"),
  infoModalBody: $("infoModalBody"),
  tagsModal: $("tagsModal"),
  tagsModalBody: $("tagsModalBody"),
  historyModal: $("historyModal"),
  historyArea: $("historyArea"),
  teamModal: $("teamModal"),
  teamModalBody: $("teamModalBody"),
  assassinModal: $("assassinModal"),
  assassinModalBody: $("assassinModalBody"),
  dealOverlay: $("dealOverlay"),
  dealCard: $("dealCard"),
  dealCardBack: $("dealCardBack"),
  dealConfirmRoleBtn: $("dealConfirmRoleBtn"),
  openTagsBtn: $("openTagsBtn"),
  openInfoBtn: $("openInfoBtn"),
  openHistoryBtn: $("openHistoryBtn"),
  infoMiniBtn: $("infoMiniBtn"),
};

const appState = {
  roomId: "",
  sessionToken: "",
  playerId: "",
  snapshot: null,
  socket: null,
  messages: [],
  lastPhase: null,
  dealShownFor: null,
  selectedTeam: [],
  pendingAssassinationTarget: "",
  commandPending: null,
};

const phaseLabels = {
  LOBBY: "大厅",
  TEAM_PROPOSAL: "队长组队",
  TEAM_VOTE: "组队投票",
  MISSION_VOTE: "任务投票",
  MISSION_RESULT_DISCUSSION: "任务复盘",
  ASSASSINATION: "刺杀",
  GAME_OVER: "终局",
};

const roleDescriptions = {
  "梅林": "你知道除莫德雷德外的邪恶方。隐藏自己，帮助正义完成三次任务。",
  "派西维尔": "你会看到梅林和莫甘娜，但无法区分两者。",
  "忠臣": "你没有额外夜间信息，需要通过发言和投票判断阵营。",
  "莫甘娜": "你会伪装成梅林干扰派西维尔判断。",
  "刺客": "若正义完成三次任务，你可以刺杀梅林来为邪恶翻盘。",
  "莫德雷德": "你属于邪恶方，并且不会被梅林看见。",
  "奥伯伦": "你属于邪恶方，但不会看见其他邪恶方，其他邪恶方也看不见你。",
};

const missingFeatureHints = {
  select_team: "组队提交尚未接入 v2 命令网关，按钮暂时不可用。",
  team_vote: "组队投票尚未接入 v2 命令网关，按钮暂时不可用。",
  mission_vote: "任务票尚未接入 v2 命令网关，按钮暂时不可用。",
  assassinate: "刺杀提交尚未接入 v2 命令网关，按钮暂时不可用。",
  continue_after_result: "任务结果后的下一轮推进尚未接入 v2 命令网关，按钮暂时不可用。",
  chat: "文字公屏尚未接入 v2 服务端消息，暂时不可发送。",
  voice: "语音客户端尚未接入 v2 页面，暂时不可点击。",
  tags: "私人标记尚未接入 v2 页面状态，暂时不可点击。",
};

window.addEventListener("load", init);

function init() {
  showLobby();
  bindEvents();
  hydrateJoinForm();
  disableUnsupportedChrome();
}

function bindEvents() {
  elements.joinBtn?.addEventListener("click", joinRoom);
  elements.roomInput?.addEventListener("keydown", submitJoinOnEnter);
  elements.nameInput?.addEventListener("keydown", submitJoinOnEnter);
  elements.copyRoomBtn?.addEventListener("click", copyInviteLink);
  elements.backBtn?.addEventListener("click", handleBackButton);
  elements.resetBtn?.addEventListener("click", () => sendCommand({type: "reset"}));
  elements.infoMiniBtn?.addEventListener("click", () => openInfoModal());
  elements.openInfoBtn?.addEventListener("click", () => openInfoModal());
  elements.openHistoryBtn?.addEventListener("click", () => openHistoryModal());
  elements.sendChatBtn?.addEventListener("click", sendChatMessage);
  elements.chatInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendChatMessage();
    }
  });
  elements.dealCard?.addEventListener("click", () => {
    elements.dealCard?.classList.toggle("flipped");
    if (elements.dealConfirmRoleBtn) elements.dealConfirmRoleBtn.disabled = false;
  });
  elements.dealConfirmRoleBtn?.addEventListener("click", hideDealOverlay);
  elements.modalBackdrop?.addEventListener("click", closeModals);
  document.querySelectorAll("[data-close-modal]").forEach((button) => {
    button.addEventListener("click", closeModals);
  });
}

function submitJoinOnEnter(event) {
  if (event.key === "Enter") joinRoom();
}

function hydrateJoinForm() {
  const params = new URLSearchParams(window.location.search);
  const roomFromUrl = normalizeRoom(params.get("room") || "");
  const lastRoom = localStorage.getItem("avalon_last_room") || "";
  const lastName = localStorage.getItem("avalon_player_name") || "";
  if (roomFromUrl) elements.roomInput.value = roomFromUrl;
  if (lastName) elements.nameInput.value = lastName;

  if (lastRoom && !roomFromUrl && elements.lastRoomCard) {
    elements.lastRoomCard.classList.remove("hidden");
    if (elements.lastRoomName) elements.lastRoomName.textContent = `房间 #${lastRoom}`;
    elements.lastRoomCard.addEventListener("click", () => {
      elements.roomInput.value = lastRoom;
      if (lastName) elements.nameInput.value = lastName;
      elements.nameInput.focus();
    });
  }

  if (roomFromUrl && lastName) {
    elements.roomInput.value = roomFromUrl;
  }
}

function disableUnsupportedChrome() {
  disableControl(elements.voiceBtn, missingFeatureHints.voice);
  disableControl(elements.listenBtn, missingFeatureHints.voice);
  disableControl(elements.openTagsBtn, missingFeatureHints.tags);
}

function disableControl(element, reason) {
  if (!element) return;
  element.disabled = true;
  element.title = reason;
  element.setAttribute("aria-disabled", "true");
}

async function joinRoom() {
  const roomId = normalizeRoom(elements.roomInput.value || "AVALON");
  const nickname = (elements.nameInput.value || "").trim().slice(0, 24);
  if (!roomId || !nickname) {
    showJoinStatus("请填写房间号和昵称。", true);
    return;
  }

  elements.joinBtn.disabled = true;
  showJoinStatus("正在进入圆桌……");
  try {
    const response = await fetch(`/api/rooms/${encodeURIComponent(roomId)}/join`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({nickname}),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || "加入房间失败。");

    appState.roomId = payload.room_id || roomId;
    appState.playerId = payload.player_id;
    appState.sessionToken = payload.session_token;
    appState.snapshot = payload.snapshot;
    localStorage.setItem("avalon_last_room", appState.roomId);
    localStorage.setItem("avalon_player_name", nickname);
    window.history.replaceState({}, "", `/?room=${encodeURIComponent(appState.roomId)}`);

    showGame();
    addSystemMessage("已进入圆桌。");
    renderSnapshot(payload.snapshot);
    connectWebSocket();
  } catch (error) {
    showJoinStatus(error.message || "加入房间失败。", true);
  } finally {
    elements.joinBtn.disabled = false;
  }
}

function connectWebSocket() {
  if (appState.socket) {
    try { appState.socket.close(); } catch (_) {}
  }
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocket(`${protocol}//${window.location.host}/ws/${encodeURIComponent(appState.roomId)}`);
  appState.socket = socket;

  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({type: "hello", session_token: appState.sessionToken}));
    addSystemMessage("实时连接已建立。");
  });
  socket.addEventListener("message", (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (_) {
      addSystemMessage("收到无法解析的实时消息。", true);
      return;
    }
    if (payload.type === "state") {
      const pendingType = appState.commandPending?.type || "";
      const acknowledged = snapshotAcknowledgesPendingCommand(payload.snapshot);
      if (acknowledged) {
        handleAcknowledgedPendingCommand(payload.snapshot);
      }
      if ((pendingType === "leave_room" && acknowledged) || snapshotMissingCurrentPlayer(payload.snapshot)) {
        leaveRoom();
        return;
      }
      appState.snapshot = payload.snapshot;
      renderSnapshot(payload.snapshot);
      return;
    }
    if (payload.type === "error") {
      setCommandPending(null, false);
      showTopError(payload.message || "服务端返回错误。");
      renderActions(appState.snapshot);
      renderChatControls(appState.snapshot);
      return;
    }
    if (payload.type === "removed") {
      setCommandPending(null, false);
      leaveRoom();
      return;
    }
    if (payload.type === "pong") {
      return;
    }
  });
  socket.addEventListener("close", () => {
    setCommandPending(null);
    addSystemMessage("实时连接已断开，刷新或重新进入房间可恢复。", true);
  });
  socket.addEventListener("error", () => {
    setCommandPending(null);
    showTopError("实时连接异常。");
  });
}

function leaveRoom() {
  if (appState.socket) {
    try { appState.socket.close(); } catch (_) {}
  }
  appState.roomId = "";
  appState.sessionToken = "";
  appState.playerId = "";
  appState.snapshot = null;
  appState.socket = null;
  appState.lastPhase = null;
  appState.dealShownFor = null;
  appState.selectedTeam = [];
  appState.pendingAssassinationTarget = "";
  appState.commandPending = null;
  hideDealOverlay();
  closeModals();
  window.history.replaceState({}, "", "/");
  showLobby();
}

async function handleBackButton() {
  if (phase(appState.snapshot) === "LOBBY" && appState.sessionToken) {
    await sendCommand({type: "leave_room"});
    return;
  }
  leaveRoom();
}

function renderSnapshot(snapshot) {
  if (!snapshot) return;
  const nextPhase = snapshot.phase_summary?.phase || "LOBBY";
  const phaseChanged = Boolean(appState.lastPhase && appState.lastPhase !== nextPhase);
  if (phaseChanged) {
    closeActionModals();
  }
  const players = normalizePlayers(snapshot);

  elements.roomCode.textContent = snapshot.room?.room_id || appState.roomId || "-";
  elements.phaseTitle.textContent = phaseLabels[nextPhase] || nextPhase;
  elements.playerCountText.textContent = `${players.length}/10`;
  renderScore(snapshot);
  renderSeats(players, snapshot);
  renderAnnouncement(snapshot, players);
  renderActions(snapshot);
  renderIdentityHint(snapshot);
  renderChat(snapshot);
  renderChatControls(snapshot);
  updateHostControls(snapshot);

  if (phaseChanged) {
    showPhaseToast(phaseLabels[nextPhase] || nextPhase);
  }
  appState.lastPhase = nextPhase;
  maybeShowDealOverlay(snapshot);
}

function renderScore(snapshot) {
  const score = snapshot.phase_summary?.score || {};
  const good = numberOr(snapshot.phase_summary?.score_good, score.good, 0);
  const evil = numberOr(snapshot.phase_summary?.score_evil, score.evil, 0);
  const goodSpan = document.createElement("span");
  goodSpan.className = "good-score";
  goodSpan.textContent = `正义 ${good}`;
  const evilSpan = document.createElement("span");
  evilSpan.className = "evil-score";
  evilSpan.textContent = `邪恶 ${evil}`;
  elements.scoreText.replaceChildren(goodSpan, document.createTextNode(" : "), evilSpan);
}

function renderSeats(players, snapshot) {
  elements.oddPlayersList.replaceChildren();
  elements.evenPlayersList.replaceChildren();
  const bySeat = new Map(players.map((player) => [player.seat, player]));
  for (let seat = 1; seat <= 10; seat += 1) {
    const card = renderSeatCard(bySeat.get(seat), seat, snapshot);
    if (seat % 2 === 1) {
      elements.oddPlayersList.append(card);
    } else {
      elements.evenPlayersList.append(card);
    }
  }
}

function renderSeatCard(player, seat, snapshot) {
  const card = document.createElement("button");
  card.type = "button";
  card.className = "seat-card";
  if (!player) card.classList.add("empty-seat");
  if (player?.player_id === appState.playerId) card.classList.add("self");
  if (player?.is_leader) card.classList.add("leader");
  if (player && currentTeam(snapshot).includes(player.player_id)) card.classList.add("team-member");
  card.disabled = !player;

  const top = document.createElement("div");
  top.className = "seat-top";
  const num = document.createElement("span");
  num.className = "seat-num";
  num.textContent = `${seat}`;
  top.append(num);

  const main = document.createElement("div");
  main.className = "seat-main";
  const name = document.createElement("div");
  name.className = "seat-name";
  name.textContent = player ? player.nickname || player.display || "玩家" : "空席";
  const tags = document.createElement("div");
  tags.className = "seat-tags";
  if (player) playerTags(player, snapshot).forEach((tag) => tags.append(renderTag(tag)));
  main.append(name, tags);
  card.append(top, main);

  if (player?.player_id === appState.playerId && snapshot.private_panel) {
    card.addEventListener("click", openRoleModal);
  }
  return card;
}

function renderTag(tag) {
  const item = document.createElement("span");
  item.className = `tag ${tag.kind}`;
  item.textContent = tag.label;
  return item;
}

function playerTags(player, snapshot) {
  const tags = [];
  if (player.player_id === appState.playerId) tags.push({kind: "self", label: "我"});
  if (player.is_host) tags.push({kind: "host", label: "房主"});
  if (player.is_leader) tags.push({kind: "leader", label: "队长"});
  if (currentTeam(snapshot).includes(player.player_id)) tags.push({kind: "team", label: "出征"});
  if (player.ready === true) tags.push({kind: "ready", label: "已准备"});
  if (player.ready === false && phase(snapshot) === "LOBBY") tags.push({kind: "not-ready", label: "未准备"});
  return tags;
}

function renderAnnouncement(snapshot, players) {
  const currentPhase = phase(snapshot);
  const summary = snapshot.phase_summary || {};
  const you = snapshot.you || {};
  const leader = players.find((player) => player.player_id === summary.leader_id);
  const team = currentTeam(snapshot).map((id) => displayName(id, players));
  let text = "等待圆桌开启。";

  if (currentPhase === "LOBBY") {
    const count = players.length;
    text = count >= 5
      ? "人数已满足开局条件。房主可以开始游戏，其他玩家可继续准备。"
      : `当前 ${count} 人，至少 5 人后可以开始游戏。`;
  } else if (currentPhase === "TEAM_PROPOSAL") {
    text = leader
      ? `${leader.display} 是本轮队长，需要选择 ${summary.required_team_size || "若干"} 名出征队员。`
      : "等待本轮队长选择出征队伍。";
  } else if (currentPhase === "TEAM_VOTE") {
    text = `队伍已提交：${team.join("、") || "暂无"}。全员需要对这支队伍投票。`;
  } else if (currentPhase === "MISSION_VOTE") {
    text = `队伍通过，出征队员提交任务票：${team.join("、") || "暂无"}。`;
  } else if (currentPhase === "MISSION_RESULT_DISCUSSION") {
    text = missionResultText(snapshot);
  } else if (currentPhase === "ASSASSINATION") {
    text = "正义已完成三次任务，刺客需要选择梅林。";
  } else if (currentPhase === "GAME_OVER") {
    text = summary.winner ? `游戏结束，${winnerLabel(summary.winner)} 获胜。` : "游戏结束。";
  }

  if (you.is_host && currentPhase !== "LOBBY") {
    text += " 房主仍可重置房间。";
  }
  elements.announcementText.textContent = text;
}

function renderActions(snapshot) {
  elements.actionArea.replaceChildren();
  if (!snapshot) {
    elements.permissionText.textContent = "等待";
    elements.actionArea.append(paragraph("等待房间状态。"));
    return;
  }

  const currentPhase = phase(snapshot);
  const actionType = snapshot.my_action?.type || "wait";
  const needsAction = actionType !== "wait" || currentPhase === "LOBBY" || currentPhase === "MISSION_RESULT_DISCUSSION";
  elements.actionPanel.classList.toggle("needs-action", needsAction);

  if (currentPhase === "LOBBY") {
    renderLobbyActions(snapshot);
    return;
  }
  if (currentPhase === "TEAM_PROPOSAL") {
    elements.permissionText.textContent = actionType === "select_team" ? "你操作" : "等待队长";
    if (actionType === "select_team") {
      elements.actionArea.append(
        paragraph(`你是本轮队长，需要选择 ${snapshot.phase_summary?.required_team_size || "若干"} 名出征队员。`),
        button("选择出征队伍", "btn btn-gold", openTeamModal),
      );
    } else {
      elements.actionArea.append(paragraph("等待队长选择出征队伍。"));
    }
    appendHostReset(snapshot);
    return;
  }
  if (currentPhase === "TEAM_VOTE") {
    elements.permissionText.textContent = actionType === "team_vote" ? "你投票" : "已提交/等待";
    appendTeamSummary(snapshot);
    if (actionType === "team_vote") {
      const row = document.createElement("div");
      row.className = "button-row";
      row.append(
        button("赞成", "btn btn-good", () => sendCommand({type: "team_vote", vote: "Approve"})),
        button("反对", "btn btn-bad", () => sendCommand({type: "team_vote", vote: "Reject"})),
      );
      elements.actionArea.append(row);
    } else {
      elements.actionArea.append(paragraph("等待所有玩家完成组队投票。"));
    }
    appendHostReset(snapshot);
    return;
  }
  if (currentPhase === "MISSION_VOTE") {
    elements.permissionText.textContent = actionType === "mission_vote" ? "你行动" : "等待队员";
    appendTeamSummary(snapshot);
    if (actionType === "mission_vote") {
      const success = button("任务成功", "btn btn-good", () => sendCommand({type: "mission_vote", vote: "Success"}));
      if (snapshot.my_action?.can_submit_fail === false) {
        elements.actionArea.append(success, paragraph("你的身份本轮只能提交任务成功。"));
      } else {
        const row = document.createElement("div");
        row.className = "button-row";
        row.append(
          success,
          button("任务失败", "btn btn-bad", () => sendCommand({type: "mission_vote", vote: "Fail"})),
        );
        elements.actionArea.append(row);
      }
    } else {
      elements.actionArea.append(paragraph("等待出征队员秘密提交任务票。"));
    }
    appendHostReset(snapshot);
    return;
  }
  if (currentPhase === "MISSION_RESULT_DISCUSSION") {
    elements.permissionText.textContent = snapshot.you?.is_host ? "房主推进" : "等待房主";
    elements.actionArea.append(paragraph(missionResultText(snapshot)));
    if (snapshot.you?.is_host) {
      elements.actionArea.append(button("进入下一轮", "btn btn-gold", () => sendCommand({type: "continue_after_result"})));
    } else {
      elements.actionArea.append(paragraph("等待房主确认结果后进入下一轮。"));
    }
    appendHostReset(snapshot);
    return;
  }
  if (currentPhase === "ASSASSINATION") {
    elements.permissionText.textContent = actionType === "assassinate" ? "你刺杀" : "等待刺客";
    if (actionType === "assassinate") {
      elements.actionArea.append(
        paragraph("你是刺客，需要选择梅林作为刺杀目标。"),
        button("选择刺杀目标", "btn btn-danger armed", openAssassinModal),
      );
    } else {
      elements.actionArea.append(paragraph("等待刺客提交刺杀目标。"));
    }
    appendHostReset(snapshot);
    return;
  }
  if (currentPhase === "GAME_OVER") {
    elements.permissionText.textContent = "结束";
    elements.actionArea.append(paragraph(`游戏结束：${winnerLabel(snapshot.phase_summary?.winner)} 获胜。`));
    appendRevealRoles(snapshot);
    appendHostReset(snapshot);
    return;
  }

  elements.permissionText.textContent = "等待";
  elements.actionArea.append(paragraph("当前阶段暂无需要你提交的操作。"));
  appendHostReset(snapshot);
}

function renderLobbyActions(snapshot) {
  const you = snapshot.you || {};
  const playerCount = normalizePlayers(snapshot).length;
  elements.permissionText.textContent = you.is_host ? "房主" : "准备";
  const ready = button(you.ready ? "取消准备" : "我已准备", you.ready ? "btn btn-secondary" : "btn btn-primary", () => {
    sendCommand({type: "ready", ready: !Boolean(you.ready)});
  });
  elements.actionArea.append(ready);

  if (you.is_host) {
    const start = button("开始游戏", "btn btn-gold", () => sendCommand({type: "start_game"}));
    start.disabled = appState.commandPending || playerCount < 5;
    start.setAttribute("aria-disabled", start.disabled ? "true" : "false");
    start.title = appState.commandPending
      ? "操作正在提交，请稍候。"
      : playerCount < 5 ? "至少 5 人后可以开始游戏。" : "开始游戏";
    elements.actionArea.append(start);
    elements.actionArea.append(button("重置房间", "btn btn-secondary", () => sendCommand({type: "reset"})));
  } else {
    elements.actionArea.append(button("退出房间", "btn btn-secondary", () => sendCommand({type: "leave_room"})));
  }

  const hint = playerCount < 5
    ? `还差 ${5 - playerCount} 人可开局。`
    : "人数已满足开局条件。";
  elements.actionArea.append(paragraph(hint));
}

function appendTeamSummary(snapshot) {
  const players = normalizePlayers(snapshot);
  const team = currentTeam(snapshot);
  const box = document.createElement("div");
  box.className = "team-summary";
  box.append(document.createTextNode("当前队伍"));
  if (team.length === 0) {
    const empty = document.createElement("span");
    empty.className = "team-chip";
    empty.textContent = "暂无";
    box.append(empty);
  } else {
    team.forEach((playerId) => {
      const chip = document.createElement("span");
      chip.className = "team-chip";
      chip.textContent = displayName(playerId, players);
      box.append(chip);
    });
  }
  elements.actionArea.append(box);
}

function openTeamModal() {
  const snapshot = appState.snapshot;
  if (!snapshot) return;
  const players = normalizePlayers(snapshot);
  const required = Number(snapshot.phase_summary?.required_team_size) || 0;
  const current = currentTeam(snapshot);
  appState.selectedTeam = current.length > 0 ? current.slice(0, required) : [];
  renderTeamModal(players, required);
  openModal(elements.teamModal);
}

function renderTeamModal(players, required) {
  elements.teamModalBody.replaceChildren();
  const progress = document.createElement("div");
  progress.className = "selection-progress";
  progress.textContent = `已选择 ${appState.selectedTeam.length}/${required || "?"}`;
  elements.teamModalBody.append(progress);

  const grid = document.createElement("div");
  grid.className = "picker-grid";
  players.forEach((player) => {
    const option = button(player.display || player.nickname || "玩家", "picker-option", () => {
      toggleTeamMember(player.player_id, required);
    });
    const selected = appState.selectedTeam.includes(player.player_id);
    option.setAttribute("aria-pressed", selected ? "true" : "false");
    if (selected) {
      option.classList.add("selected");
    }
    grid.append(option);
  });
  elements.teamModalBody.append(grid);

  const submit = button("确认出征队伍", "btn btn-gold", submitSelectedTeam);
  submit.disabled = appState.commandPending || appState.selectedTeam.length !== required;
  submit.setAttribute("aria-disabled", submit.disabled ? "true" : "false");
  elements.teamModalBody.append(submit);
}

function toggleTeamMember(playerId, required) {
  if (appState.selectedTeam.includes(playerId)) {
    appState.selectedTeam = appState.selectedTeam.filter((id) => id !== playerId);
  } else {
    if (appState.selectedTeam.length >= required) {
      showTopError(`本轮只能选择 ${required} 名出征队员。`);
      return;
    }
    appState.selectedTeam = [...appState.selectedTeam, playerId];
  }
  renderTeamModal(normalizePlayers(appState.snapshot), required);
}

function submitSelectedTeam() {
  const required = Number(appState.snapshot?.phase_summary?.required_team_size) || 0;
  if (appState.selectedTeam.length !== required) {
    showTopError(`请先选择 ${required} 名出征队员。`);
    return;
  }
  closeModals();
  sendCommand({type: "select_team", team: appState.selectedTeam});
}

function openAssassinModal() {
  const snapshot = appState.snapshot;
  if (!snapshot) return;
  appState.pendingAssassinationTarget = "";
  renderAssassinModal(normalizePlayers(snapshot));
  openModal(elements.assassinModal);
}

function renderAssassinModal(players) {
  elements.assassinModalBody.replaceChildren();
  const grid = document.createElement("div");
  grid.className = "picker-grid";
  players.forEach((player) => {
    const option = button(player.display || player.nickname || "玩家", "picker-option danger-select", () => {
      appState.pendingAssassinationTarget = player.player_id;
      renderAssassinModal(normalizePlayers(appState.snapshot));
    });
    const selected = appState.pendingAssassinationTarget === player.player_id;
    option.setAttribute("aria-pressed", selected ? "true" : "false");
    if (selected) {
      option.classList.add("selected");
    }
    grid.append(option);
  });
  elements.assassinModalBody.append(grid);

  const submit = button("确认刺杀", "btn btn-danger armed", submitAssassination);
  submit.disabled = appState.commandPending || !appState.pendingAssassinationTarget;
  submit.setAttribute("aria-disabled", submit.disabled ? "true" : "false");
  elements.assassinModalBody.append(submit);
}

function submitAssassination() {
  const targetId = appState.pendingAssassinationTarget;
  if (!targetId) {
    showTopError("请先选择刺杀目标。");
    return;
  }
  closeModals();
  sendCommand({type: "assassinate", target_id: targetId});
}

function appendRevealRoles(snapshot, container = elements.actionArea) {
  const roles = Array.isArray(snapshot?.reveal_roles) ? snapshot.reveal_roles : [];
  if (roles.length === 0 || !container) return;

  const title = document.createElement("div");
  title.className = "modal-section-title";
  title.textContent = "终局身份公开";
  const list = document.createElement("div");
  list.className = "reveal-list";
  roles.forEach((item) => {
    const row = document.createElement("div");
    const side = item.side === "evil" ? "evil" : "good";
    row.className = `reveal-row ${side}`;
    row.textContent = `${item.display || displayName(item.player_id)}：${item.role || "未知身份"}`;
    list.append(row);
  });
  container.append(title, list);
}

function appendHostReset(snapshot) {
  if (!snapshot.you?.is_host) return;
  elements.actionArea.append(button("重置房间", "btn btn-secondary", () => sendCommand({type: "reset"})));
}

function updateHostControls(snapshot) {
  const isHost = Boolean(snapshot?.you?.is_host);
  elements.resetBtn?.classList.toggle("hidden", !isHost);
}

function renderIdentityHint(snapshot) {
  if (!snapshot.private_panel) {
    elements.identityHint.textContent = "ⓘ 游戏开始后可点击自己的席位查看身份牌";
    return;
  }
  const role = snapshot.private_panel.role || "未知身份";
  elements.identityHint.textContent = `ⓘ 你的身份：${role}。点击自己的席位可再次查看。`;
}

function renderChat(snapshot) {
  elements.chatMessages.replaceChildren();
  const serverMessages = Array.isArray(snapshot?.chat_history) ? snapshot.chat_history.slice(-40) : null;
  const messages = serverMessages || appState.messages.slice(-40);
  if (messages.length === 0) {
    elements.chatMessages.append(chatLine("系统", "暂无公屏消息。", true));
    return;
  }
  messages.forEach((message) => {
    elements.chatMessages.append(chatLine(message.author_display || message.author || "系统", message.text, message.error));
  });
}

function renderChatControls(snapshot) {
  const canSendText = Boolean(snapshot?.speaker_state?.can_send_text);
  const disabled = !canSendText || Boolean(appState.commandPending) || !appState.sessionToken;
  if (elements.chatInput) {
    elements.chatInput.disabled = disabled;
    elements.chatInput.setAttribute("aria-disabled", disabled ? "true" : "false");
    elements.chatInput.placeholder = canSendText ? "输入公屏消息" : "当前阶段禁止发言";
    elements.chatInput.title = canSendText ? "发送公屏消息" : "组队投票和任务投票阶段禁言。";
  }
  if (elements.sendChatBtn) {
    elements.sendChatBtn.disabled = disabled;
    elements.sendChatBtn.setAttribute("aria-disabled", disabled ? "true" : "false");
    elements.sendChatBtn.title = canSendText ? "发送" : "当前阶段禁止发言";
  }
  if (elements.chatStatusText) {
    elements.chatStatusText.textContent = canSendText ? "可发言" : "禁言中";
  }
}

async function sendChatMessage() {
  const text = (elements.chatInput?.value || "").trim();
  if (!text) return;
  if (text.length > 300) {
    showTopError("消息不能超过 300 字。");
    return;
  }
  await sendCommand({type: "send_chat", text});
}

function chatLine(author, text, muted = false) {
  const line = document.createElement("div");
  line.className = muted ? "line muted" : "line";
  const name = document.createElement("span");
  name.className = "chat-name";
  name.textContent = `${author}：`;
  const body = document.createElement("span");
  body.textContent = text;
  line.append(name, body);
  return line;
}

function openRoleModal() {
  renderRoleInto(elements.roleModalBody, appState.snapshot?.private_panel);
  openModal(elements.roleModal);
}

function openInfoModal() {
  const snapshot = appState.snapshot;
  elements.infoModalBody.replaceChildren();
  if (!snapshot) {
    elements.infoModalBody.append(paragraph("尚未加入房间。"));
    openModal(elements.infoModal);
    return;
  }
  const table = document.createElement("div");
  table.className = "info-table";
  const players = normalizePlayers(snapshot);
  const summary = snapshot.phase_summary || {};
  [
    ["房间", snapshot.room?.room_id || appState.roomId || "-"],
    ["阶段", phaseLabels[phase(snapshot)] || phase(snapshot)],
    ["人数", `${players.length}/10`],
    ["本轮", summary.round_number ? `第 ${summary.round_number} 轮` : "未开始"],
    ["队长", displayName(summary.leader_id, players)],
    ["队伍人数", summary.required_team_size || "未定"],
    ["当前队伍", currentTeam(snapshot).map((id) => displayName(id, players)).join("、") || "暂无"],
    ["比分", `正义 ${summary.score_good || 0} : 邪恶 ${summary.score_evil || 0}`],
  ].forEach(([label, value]) => table.append(infoRow(label, value)));
  elements.infoModalBody.append(table);
  appendGovernanceControls(snapshot, players);
  appendRevealRoles(snapshot, elements.infoModalBody);
  openModal(elements.infoModal);
}

function appendGovernanceControls(snapshot, players) {
  if (!snapshot.you?.is_host || phase(snapshot) !== "LOBBY") return;
  const targets = players.filter((player) => !player.is_host);
  if (targets.length === 0) return;

  const sectionTitle = document.createElement("h3");
  sectionTitle.className = "modal-section-title";
  sectionTitle.textContent = "大厅管理";
  const list = document.createElement("div");
  list.className = "governance-list";
  targets.forEach((player) => {
    const row = document.createElement("div");
    row.className = "governance-row";
    const label = document.createElement("span");
    label.textContent = player.display;
    const actions = document.createElement("div");
    actions.className = "governance-actions";
    actions.append(
      button("转让房主", "mini-btn", () => {
        closeModals();
        sendCommand({type: "transfer_host", target_id: player.player_id});
      }),
      button("踢出", "mini-btn danger", () => {
        closeModals();
        sendCommand({type: "kick_player", target_id: player.player_id});
      }),
    );
    row.append(label, actions);
    list.append(row);
  });
  elements.infoModalBody.append(sectionTitle, list);
}

function openHistoryModal() {
  elements.historyArea.replaceChildren();
  const timeline = appState.snapshot?.public_timeline || [];
  const stack = document.createElement("div");
  stack.className = "history-paper-stack";
  const paper = document.createElement("div");
  paper.className = "history-paper";
  const title = document.createElement("h3");
  title.textContent = "公开历史";
  paper.append(title);
  if (timeline.length === 0) {
    const line = document.createElement("div");
    line.className = "paper-line muted";
    line.textContent = "公开历史尚未接入事件投影。";
    paper.append(line);
  } else {
    timeline.forEach((item) => {
      const line = document.createElement("div");
      line.className = "paper-line";
      line.textContent = item.summary || item.event_type || String(item);
      paper.append(line);
    });
  }
  stack.append(paper);
  elements.historyArea.append(stack);
  openModal(elements.historyModal);
}

function infoRow(label, value) {
  const row = document.createElement("div");
  row.className = "info-row";
  const labelEl = document.createElement("span");
  labelEl.className = "info-label";
  labelEl.textContent = label;
  const valueEl = document.createElement("span");
  valueEl.className = "info-value";
  valueEl.textContent = value || "-";
  row.append(labelEl, valueEl);
  return row;
}

function maybeShowDealOverlay(snapshot) {
  const role = snapshot.private_panel?.role;
  if (!role) return;
  const key = `${snapshot.room?.room_id || appState.roomId}:${appState.playerId}:${role}`;
  if (appState.dealShownFor === key) return;
  appState.dealShownFor = key;
  renderRoleInto(elements.dealCardBack, snapshot.private_panel, true);
  elements.dealCard?.classList.remove("flipped");
  if (elements.dealConfirmRoleBtn) elements.dealConfirmRoleBtn.disabled = true;
  elements.dealOverlay?.classList.remove("hidden");
}

function renderRoleInto(container, privatePanel, compact = false) {
  container.replaceChildren();
  if (!privatePanel) {
    container.append(paragraph("身份信息尚未生成。"));
    return;
  }
  const side = privatePanel.side === "evil" ? "evil" : "good";
  const card = document.createElement("div");
  card.className = `deal-role-card ${side}`;
  const emblem = document.createElement("div");
  emblem.className = "deal-role-emblem";
  emblem.textContent = side === "evil" ? "☠" : "✦";
  const name = document.createElement("div");
  name.className = `deal-role-name ${side === "evil" ? "info-evil" : "info-good"}`;
  name.textContent = privatePanel.role || "未知";
  const sideText = document.createElement("div");
  sideText.className = "deal-role-side";
  sideText.textContent = side === "evil" ? "邪恶阵营" : "正义阵营";
  const scroll = document.createElement("div");
  scroll.className = "deal-role-scroll";
  scroll.append(roleBlock("说明", roleDescriptions[privatePanel.role] || "根据发言与投票推进游戏。"));
  const visible = privatePanel.visible_players || [];
  scroll.append(roleBlock(
    "你可见的玩家",
    visible.length > 0 ? visible.map((player) => player.display || player.player_id).join("、") : "无额外可见信息",
  ));
  card.append(emblem, name, sideText, scroll);
  if (!compact) {
    const title = document.createElement("h2");
    title.className = "modal-title";
    title.textContent = "你的身份";
    container.append(title);
  }
  container.append(card);
}

function roleBlock(label, value) {
  const block = document.createElement("div");
  const labelEl = document.createElement("b");
  labelEl.textContent = label;
  const valueEl = document.createElement("span");
  valueEl.textContent = value;
  block.append(labelEl, valueEl);
  return block;
}

function hideDealOverlay() {
  elements.dealOverlay?.classList.add("hidden");
}

function openModal(modal) {
  closeModals();
  elements.modalBackdrop?.classList.remove("hidden");
  modal?.classList.remove("hidden");
}

function closeModals() {
  elements.modalBackdrop?.classList.add("hidden");
  [elements.roleModal, elements.infoModal, elements.tagsModal, elements.historyModal, elements.teamModal, elements.assassinModal].forEach((modal) => {
    modal?.classList.add("hidden");
  });
}

function closeActionModals() {
  const actionModalOpen = [elements.teamModal, elements.assassinModal].some((modal) => {
    return modal && !modal.classList.contains("hidden");
  });
  elements.teamModal?.classList.add("hidden");
  elements.assassinModal?.classList.add("hidden");
  if (actionModalOpen) elements.modalBackdrop?.classList.add("hidden");
  appState.selectedTeam = [];
  appState.pendingAssassinationTarget = "";
}

async function sendCommand(command) {
  if (!appState.sessionToken || !appState.roomId) {
    showTopError("请先加入房间。");
    return false;
  }
  if (appState.commandPending) {
    showTopError("操作正在提交，请稍候。");
    return false;
  }
  const message = {
    type: "command",
    request_id: makeRequestId(),
    command,
  };
  setCommandPending(createPendingCommand(command, message.request_id));
  clearPendingAfterNoopResetDebounce(message.request_id);
  if (appState.socket?.readyState === WebSocket.OPEN) {
    try {
      appState.socket.send(JSON.stringify(message));
    } catch (_) {
      setCommandPending(null);
      showTopError("操作发送失败，请重试。");
      return false;
    }
    return true;
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
    if (!response.ok) throw new Error(payload.detail || "操作失败。");
    const acknowledged = snapshotAcknowledgesPendingCommand(payload.snapshot);
    if (acknowledged) {
      handleAcknowledgedPendingCommand(payload.snapshot);
    }
    if (command.type === "leave_room") {
      leaveRoom();
      return true;
    }
    appState.snapshot = payload.snapshot;
    renderSnapshot(payload.snapshot);
    return true;
  } catch (error) {
    showTopError(error.message || "操作失败。");
    return false;
  } finally {
    setCommandPending(null);
  }
}

function button(label, className, onClick) {
  const item = document.createElement("button");
  item.type = "button";
  item.className = className;
  item.textContent = label;
  if (appState.commandPending) {
    item.disabled = true;
    item.setAttribute("aria-disabled", "true");
  }
  item.addEventListener("click", onClick);
  return item;
}

function disabledButton(label, className, reason) {
  const item = document.createElement("button");
  item.type = "button";
  item.className = className;
  item.textContent = label;
  item.disabled = true;
  item.title = reason;
  return item;
}

function paragraph(text) {
  const item = document.createElement("p");
  item.textContent = text;
  return item;
}

function normalizePlayers(snapshot) {
  if (Array.isArray(snapshot?.participants)) {
    return snapshot.participants
      .slice()
      .sort((a, b) => Number(a.seat || 0) - Number(b.seat || 0))
      .map((participant) => ({
        player_id: participant.player_id,
        seat: Number(participant.seat) || 0,
        nickname: participant.nickname || "玩家",
        display: `${participant.seat || "?"}号-${participant.nickname || "玩家"}`,
        is_host: Boolean(participant.is_host),
        is_leader: participant.player_id === snapshot.phase_summary?.leader_id,
        ready: Boolean(participant.ready),
      }));
  }

  if (Array.isArray(snapshot?.players)) {
    return snapshot.players.map((player, index) => {
      const parsed = parseDisplay(player.display);
      const seat = Number(player.seat || parsed.seat || index + 1);
      const nickname = player.nickname || parsed.nickname || player.display || "玩家";
      return {
        player_id: player.player_id,
        seat,
        nickname,
        display: player.display || `${seat}号-${nickname}`,
        is_host: Boolean(player.is_host) || player.player_id === snapshot.room?.host_id,
        is_leader: Boolean(player.is_leader) || player.player_id === snapshot.phase_summary?.leader_id,
        ready: undefined,
      };
    });
  }

  return [];
}

function parseDisplay(display) {
  const match = String(display || "").match(/^(\d+)号-(.*)$/);
  if (!match) return {seat: null, nickname: display || ""};
  return {seat: Number(match[1]), nickname: match[2]};
}

function currentTeam(snapshot) {
  return Array.isArray(snapshot?.phase_summary?.current_team) ? snapshot.phase_summary.current_team : [];
}

function phase(snapshot) {
  return snapshot?.phase_summary?.phase || "LOBBY";
}

function displayName(playerId, players = normalizePlayers(appState.snapshot)) {
  if (!playerId) return "未定";
  const player = players.find((item) => item.player_id === playerId);
  return player?.display || player?.nickname || playerId;
}

function winnerLabel(winner) {
  if (winner === "good") return "正义方";
  if (winner === "evil") return "邪恶方";
  return "未知阵营";
}

function missionResultText(snapshot) {
  const result = snapshot?.phase_summary?.mission_result;
  if (!result) return "任务结果已结算。";
  const round = result.round_number ? `第 ${result.round_number} 轮` : "本轮";
  let outcome = result.succeeded ? "任务成功" : "任务失败";
  if (typeof result.succeeded !== "boolean") {
    outcome = "任务已结算";
  }
  const failCount = numberOr(result.fail_count, 0);
  const requiredFailCount = numberOr(result.required_fail_count, 1);
  const good = numberOr(result.score_good, snapshot?.phase_summary?.score_good, 0);
  const evil = numberOr(result.score_evil, snapshot?.phase_summary?.score_evil, 0);
  return `${round}${outcome}，失败票 ${failCount}/${requiredFailCount}，比分 正义 ${good} : 邪恶 ${evil}。`;
}

function numberOr(...values) {
  for (const value of values) {
    if (typeof value === "number" && Number.isFinite(value)) return value;
  }
  return 0;
}

function normalizeRoom(value) {
  return String(value || "")
    .trim()
    .toUpperCase()
    .replace(/[^A-Z0-9_-]/g, "")
    .slice(0, 24);
}

function makeRequestId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID().slice(0, 64);
  return `r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function createPendingCommand(command, requestId) {
  const pendingCommand = {...command};
  if (Array.isArray(command?.team)) pendingCommand.team = command.team.slice();
  const snapshot = appState.snapshot;
  const phaseBefore = phase(snapshot);
  const hadReadyPlayersBefore = normalizePlayers(snapshot).some((player) => player.ready === true);
  return {
    type: pendingCommand.type || "unknown",
    command: pendingCommand,
    requestId,
    startedAt: Date.now(),
    phaseBefore,
    hadReadyPlayersBefore,
    actorId: snapshot?.you?.player_id || appState.playerId,
  };
}

function snapshotAcknowledgesPendingCommand(snapshot) {
  const pending = appState.commandPending;
  if (!pending || !snapshot) return false;

  const pendingCommand = pending.command || {};
  const snapshotPhase = phase(snapshot);
  if (pending.type === "ready") {
    return snapshot.you?.ready === pendingCommand.ready;
  }
  if (pending.type === "start_game") {
    return snapshotPhase !== "LOBBY";
  }
  if (pending.type === "reset") {
    if (pending.phaseBefore !== "LOBBY") {
      return snapshotPhase === "LOBBY";
    }
    if (pending.hadReadyPlayersBefore) {
      return participantsAllUnready(snapshot);
    }
    return false;
  }
  if (pending.type === "send_chat") {
    return Array.isArray(snapshot.chat_history) && snapshot.chat_history.some((message) => {
      return message.request_id === pending.requestId && message.author_id === pending.actorId;
    });
  }
  if (pending.type === "kick_player") {
    return !normalizePlayers(snapshot).some((player) => player.player_id === pendingCommand.target_id);
  }
  if (pending.type === "transfer_host") {
    return snapshot.room?.host_id === pendingCommand.target_id;
  }
  if (pending.type === "leave_room") {
    return !snapshot.you || !normalizePlayers(snapshot).some((player) => player.player_id === pending.actorId);
  }
  if (pending.type === "select_team") {
    return snapshotPhase !== "TEAM_PROPOSAL" || samePlayerSet(currentTeam(snapshot), pendingCommand.team);
  }
  if (pending.type === "team_vote") {
    return snapshotPhase !== "TEAM_VOTE" || snapshot.my_action?.type !== "team_vote";
  }
  if (pending.type === "mission_vote") {
    return snapshotPhase !== "MISSION_VOTE" || snapshot.my_action?.type !== "mission_vote";
  }
  if (pending.type === "continue_after_result") {
    return snapshotPhase !== "MISSION_RESULT_DISCUSSION";
  }
  if (pending.type === "assassinate") {
    return snapshotPhase === "GAME_OVER";
  }

  // Future P1 commands may add command-specific acknowledgement rules.
  return true;
}

function handleAcknowledgedPendingCommand(snapshot) {
  const pending = appState.commandPending;
  if (!pending) return;
  if (pending.type === "send_chat" && elements.chatInput && elements.chatInput.value.trim() === pending.command.text) {
    elements.chatInput.value = "";
  }
  setCommandPending(null, false);
}

function samePlayerSet(left, right) {
  if (!Array.isArray(left) || !Array.isArray(right) || left.length !== right.length) return false;
  const rightSet = new Set(right);
  return left.every((playerId) => rightSet.has(playerId));
}

function participantsAllUnready(snapshot) {
  const players = normalizePlayers(snapshot);
  return players.length > 0 && players.every((player) => player.ready !== true);
}

function snapshotMissingCurrentPlayer(snapshot) {
  if (!appState.playerId || !Array.isArray(snapshot?.participants)) return false;
  return !snapshot.participants.some((participant) => participant.player_id === appState.playerId);
}

function clearPendingAfterNoopResetDebounce(requestId) {
  const pending = appState.commandPending;
  if (pending?.type !== "reset" || pending.phaseBefore !== "LOBBY" || pending.hadReadyPlayersBefore) return;

  // Reset while already in a clean lobby has no request-id acknowledgement in WS state;
  // this timeout only keeps rapid duplicate clicks from producing multiple reset commands.
  window.setTimeout(() => {
    if (appState.commandPending?.requestId === requestId) {
      setCommandPending(null);
    }
  }, 1000);
}

function setCommandPending(pending, rerender = true) {
  appState.commandPending = pending;
  if (rerender && appState.snapshot) {
    renderActions(appState.snapshot);
    renderChatControls(appState.snapshot);
  }
}

function showLobby() {
  elements.joinView?.classList.remove("hidden");
  elements.gameView?.classList.add("hidden");
}

function showGame() {
  elements.joinView?.classList.add("hidden");
  elements.gameView?.classList.remove("hidden");
}

function showJoinStatus(message, isError = false) {
  const existing = $("joinStatusText");
  if (existing) {
    existing.textContent = message;
    existing.classList.toggle("error-text", isError);
    return;
  }
  addSystemMessage(message, isError);
}

function showTopError(message) {
  if (!elements.errorBox) return;
  elements.errorBox.textContent = message;
  elements.errorBox.classList.remove("hidden");
  addSystemMessage(message, true);
  window.setTimeout(() => {
    elements.errorBox?.classList.add("hidden");
  }, 4200);
}

function addSystemMessage(text, error = false) {
  appState.messages.push({author: error ? "错误" : "系统", text, error});
  renderChat();
}

function showPhaseToast(label) {
  if (!elements.phaseToast) return;
  elements.phaseToast.textContent = label;
  elements.phaseToast.classList.remove("hidden");
  window.setTimeout(() => elements.phaseToast?.classList.add("hidden"), 1800);
}

async function copyInviteLink() {
  const room = appState.roomId || normalizeRoom(elements.roomInput?.value || "");
  if (!room) {
    showTopError("请先进入或填写房间号。");
    return;
  }
  const url = `${window.location.origin}/?room=${encodeURIComponent(room)}`;
  try {
    await navigator.clipboard.writeText(url);
    addSystemMessage("邀请链接已复制。");
  } catch (_) {
    showTopError(url);
  }
}
