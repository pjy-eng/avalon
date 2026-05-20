from __future__ import annotations

import asyncio
import contextlib
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import string
import random
import urllib.request
import urllib.error
from typing import Any, Dict, List, Optional, Set

try:
    import redis.asyncio as redis
except Exception:  # Redis is optional for local development.
    redis = None

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
from fastapi.middleware.cors import CORSMiddleware
import jwt

from avalon_engine import AvalonGame, Phase


MAX_CHAT_HISTORY = 120
HEARTBEAT_INTERVAL = 5
CLIENT_TIMEOUT = 15
ROOM_TTL_SECONDS = 300
ROOM_PERSIST_TTL_SECONDS = 60 * 60 * 6
WS_SEND_TIMEOUT = 3
REDIS_SAVE_RETRIES = 2
REDIS_OPERATION_TIMEOUT = 8
CRITICAL_PERSIST_EVENTS = {
    "toggle_ready", "start_game", "select_team", "speaker_finished",
    "finish_free_discussion", "team_vote", "mission_vote", "continue_after_result",
    "assassin_target", "kick_player", "reset_room"
}


class RedisPersistenceError(RuntimeError):
    pass


@dataclass
class PlayerRecord:
    id: str
    name: str
    seat: int
    connected: bool = True


@dataclass
class Room:
    room_id: str
    host_id: Optional[str] = None
    players: Dict[str, PlayerRecord] = field(default_factory=dict)
    sockets: Dict[str, WebSocket] = field(default_factory=dict)
    game: Optional[AvalonGame] = None
    chat_history: List[Dict[str, Any]] = field(default_factory=list)
    speaking_ids: Set[str] = field(default_factory=set)
    ready_ids: Set[str] = field(default_factory=set)
    last_seen: Dict[str, float] = field(default_factory=dict)
    disconnected_at: Dict[str, float] = field(default_factory=dict)
    expire_at: Optional[float] = None
    game_seq: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def player_order(self) -> List[str]:
        return [pid for pid, _p in sorted(self.players.items(), key=lambda kv: kv[1].seat)]

    def player_names(self) -> Dict[str, str]:
        return {pid: p.name for pid, p in self.players.items()}

    def public_players(self) -> List[Dict[str, Any]]:
        order = self.player_order()
        label_by_id = {pid: f"Player_{i+1}" for i, pid in enumerate(order)}
        return [
            {
                "id": pid,
                "name": self.players[pid].name,
                "seat": self.players[pid].seat,
                "label": label_by_id[pid],
                "connected": self.players[pid].connected,
                "is_host": pid == self.host_id,
                "is_speaking": pid in self.speaking_ids,
                "is_ready": pid in self.ready_ids or pid == self.host_id,
            }
            for pid in order
        ]

    def lobby_snapshot(self, for_player: str) -> Dict[str, Any]:
        count = len(self.players)
        ready_required = max(0, count - 1)
        ready_count = len([pid for pid in self.players if pid != self.host_id and pid in self.ready_ids])
        all_connected = all(p.connected for p in self.players.values())
        all_ready = ready_count == ready_required
        can_start = 5 <= count <= 10 and for_player == self.host_id and all_ready and all_connected
        announcement = f"🏰 房间 {self.room_id} 已开启。当前 {count}/10 名玩家入座。"
        return {
            "current_phase": "LOBBY",
            "control_signal": {
                "current_phase": "LOBBY",
                "round": None,
                "leader": None,
                "leader_id": None,
                "active_speaker": None,
                "active_speaker_id": None,
                "speaker_queue": [],
                "speaker_queue_ids": [],
                "required_team_size": None,
                "current_team": [],
                "current_team_ids": [],
                "mic_status": "UNMUTE_ALL",
                "chat_status": "OPEN_FOR_ALL",
                "vote_status": "CLOSED",
                "mission_vote_status": "CLOSED",
                "assassination_status": "CLOSED",
                "game_score": {"good": 0, "evil": 0},
                "failed_proposals": 0,
                "public_result": None,
                "personal_audio_allowed": True,
                "speaking_ids": list(self.speaking_ids),
                "ready_count": ready_count,
                "ready_required": ready_required,
                "all_ready": all_ready,
            },
            "public_announcement": announcement,
            "players": self.public_players(),
            "private_info": {},
            "permissions": {
                "is_host": for_player == self.host_id,
                "can_start_game": can_start,
                "can_chat": True,
                "can_speak": True,
                "can_kick": for_player == self.host_id,
                "can_toggle_ready": for_player != self.host_id,
                "is_ready": for_player in self.ready_ids or for_player == self.host_id,
                "ready_count": ready_count,
                "ready_required": ready_required,
                "all_ready": all_ready,
                "all_connected": all_connected,
            },
            "mission_result_history": [],
            "team_vote_history": [],
            "winner": None,
            "error_message": None,
            "reveal_roles": [],
            "game_seq": self.game_seq,
        }

    def snapshot_for(self, player_id: str) -> Dict[str, Any]:
        if not self.game:
            state = self.lobby_snapshot(player_id)
        else:
            # Keep player names synced for reconnect/name changes before game start.
            self.game.player_names = self.player_names()
            state = self.game.snapshot(
                for_player=player_id,
                players_public=self.public_players(),
                host_id=self.host_id,
            )
            state["control_signal"]["speaking_ids"] = list(self.speaking_ids)
            state["game_seq"] = self.game_seq
            # 房主保留重置权；本轮队长拥有游戏内主持权。
            state["permissions"]["can_kick"] = False
        return {
            "type": "state",
            "room_id": self.room_id,
            "you": {
                "id": player_id,
                "name": self.players[player_id].name,
                "seat": self.players[player_id].seat,
                "is_host": player_id == self.host_id,
            },
            "state": state,
            "chat_history": self.chat_history[-MAX_CHAT_HISTORY:],
            "server_time": datetime.now(timezone.utc).isoformat(),
        }


rooms: Dict[str, Room] = {}
redis_client = None


def redis_rest_configured() -> bool:
    return bool(os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"))


def make_redis_client():
    redis_url = os.getenv("REDIS_URL")
    if not (redis and redis_url):
        return None
    return redis.from_url(
        redis_url,
        decode_responses=True,
        socket_timeout=REDIS_OPERATION_TIMEOUT,
        socket_connect_timeout=REDIS_OPERATION_TIMEOUT,
        health_check_interval=30,
        socket_keepalive=True,
        retry_on_timeout=True,
    )


async def get_redis_client():
    global redis_client
    if redis_client is None:
        redis_client = make_redis_client()
    return redis_client


async def reset_redis_client():
    global redis_client
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass
    redis_client = make_redis_client()
    return redis_client


app = FastAPI(title="Avalon Online AI Judge", version="15.2.0-strict-recovery")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.head("/")
async def head_index() -> Dict[str, Any]:
    return {}


@app.on_event("startup")
async def startup_tasks() -> None:
    global redis_client
    redis_client = make_redis_client()
    # Do not fail local development if Redis is unavailable, but test the connection early
    # so Render logs show configuration problems before a game starts.
    if redis_rest_configured():
        try:
            await redis_rest_command(["PING"])
            print("[redis] Upstash REST persistence ready")
        except Exception as exc:
            print(f"[redis] REST ping failed: {exc}")
    elif redis_client is not None:
        try:
            await redis_client.ping()
            print("[redis] TCP persistence ready")
        except Exception as exc:
            print(f"[redis] TCP ping failed: {exc}")
            await reset_redis_client()
    else:
        print("[redis] persistence not configured; local memory mode only")
    asyncio.create_task(room_cleanup_loop())


@app.get("/health")
async def health() -> Dict[str, Any]:
    return {"ok": True, "rooms": len(rooms), "livekit_configured": livekit_configured(), "redis_configured": bool(redis_client) or redis_rest_configured()}


@app.head("/health")
async def head_health() -> Dict[str, Any]:
    return {}


@app.get("/api/livekit-token")
async def livekit_token(
    room_id: str = Query(..., min_length=1, max_length=24),
    player_id: str = Query(..., min_length=1, max_length=80),
) -> Dict[str, Any]:
    """Issue a short-lived LiveKit join token for one Avalon player.

    The frontend connects all players in the same Avalon room to one LiveKit
    audio room. API secret stays on the backend; the browser only receives a
    signed token.
    """
    if not livekit_configured():
        raise HTTPException(
            status_code=503,
            detail="LiveKit 未配置。请在 Render 环境变量设置 LIVEKIT_URL、LIVEKIT_API_KEY、LIVEKIT_API_SECRET。",
        )

    room_key = normalize_room(room_id)
    pid = sanitize_id(player_id)
    room = await get_room(room_key, create=False)
    if room is None and persistence_configured():
        raise HTTPException(status_code=503, detail="房间恢复服务暂时不可用，语音 token 暂停签发。")
    if not room or pid not in room.players:
        raise HTTPException(status_code=403, detail="玩家尚未加入该房间，不能签发语音 token。")

    livekit_room = f"avalon-{room_key}"
    name = f"{room.players[pid].seat}号-{room.players[pid].name}"
    now = int(time.time())
    payload = {
        "iss": os.environ["LIVEKIT_API_KEY"],
        "sub": pid,
        "name": name,
        "nbf": now - 5,
        "exp": now + 60 * 60 * 6,
        "metadata": json.dumps({"avalon_room": room_key, "player_id": pid}, ensure_ascii=False),
        "video": {
            "room": livekit_room,
            "roomJoin": True,
            "canPublish": True,
            "canSubscribe": True,
            "canPublishData": True,
            "canPublishSources": ["microphone"],
        },
    }
    token = jwt.encode(payload, os.environ["LIVEKIT_API_SECRET"], algorithm="HS256")
    return {
        "enabled": True,
        "url": os.environ["LIVEKIT_URL"],
        "token": token,
        "room": livekit_room,
        "identity": pid,
    }


def livekit_configured() -> bool:
    return bool(os.getenv("LIVEKIT_URL") and os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET"))


@app.get("/{full_path:path}", response_class=HTMLResponse)
async def spa_fallback(full_path: str) -> str:
    """Serve the frontend for mobile browsers / copied links that hit a non-API path.

    This prevents Safari/WeChat/Android browsers from showing a raw 404 page when
    they open the bare domain or a cached deep link. WebSocket and /static routes
    are declared above and remain unaffected.
    """
    if full_path.startswith("static/") or full_path.startswith("ws/") or full_path == "health":
        return "Not Found"
    with open(STATIC_DIR / "index.html", "r", encoding="utf-8") as f:
        return f.read()


@app.websocket("/ws/{room_id}")
async def websocket_endpoint(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    room_id = normalize_room(room_id)
    room = await get_room(room_id, create=True)
    if room is None:
        await websocket.send_json({"type": "error", "message": "房间恢复服务暂时不可用，请稍后重试。为避免丢局，系统没有创建新房间。"})
        await websocket.close()
        return
    player_id: Optional[str] = None
    try:
        join_raw = await websocket.receive_text()
        join_msg = json.loads(join_raw)
        if join_msg.get("type") != "join":
            await websocket.send_json({"type": "error", "message": "第一条消息必须是 join。"})
            await websocket.close()
            return
        player_id = sanitize_id(join_msg.get("player_id") or "")
        name = sanitize_name(join_msg.get("name") or "玩家")
        if not player_id:
            await websocket.send_json({"type": "error", "message": "缺少 player_id。"})
            await websocket.close()
            return
        async with room.lock:
            # If the game already started, only existing players may reconnect.
            if room.game and player_id not in room.players:
                await websocket.send_json({"type": "error", "message": "游戏已经开始，新玩家不能中途加入。"})
                await websocket.close()
                return
            if player_id not in room.players:
                if len(room.players) >= 10:
                    await websocket.send_json({"type": "error", "message": "房间已满，最多 10 人。"})
                    await websocket.close()
                    return
                seat = next_available_seat(room)
                room.players[player_id] = PlayerRecord(id=player_id, name=name, seat=seat, connected=True)
                if not room.host_id:
                    room.host_id = player_id
            else:
                room.players[player_id].name = name
                room.players[player_id].connected = True
            # Replace old socket for same player.
            old = room.sockets.get(player_id)
            if old and old is not websocket:
                try:
                    await old.close()
                except Exception:
                    pass
            room.sockets[player_id] = websocket
            room.last_seen[player_id] = time.time()
            room.disconnected_at.pop(player_id, None)
            room.expire_at = None
        join_saved = await save_room(room, strict=True)
        if not join_saved:
            await websocket.send_json({"type": "error", "message": "房间状态保存失败，暂时无法稳定加入。请稍后重试。"})
        await broadcast_state(room)

        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=HEARTBEAT_INTERVAL)
                msg = json.loads(raw)
                async with room.lock:
                    room.last_seen[player_id] = time.time()
                    room.disconnected_at.pop(player_id, None)
                    room.expire_at = None
                await handle_message(room, player_id, msg)
            except asyncio.TimeoutError:
                now = time.time()
                if now - room.last_seen.get(player_id, now) > CLIENT_TIMEOUT:
                    raise WebSocketDisconnect()
                try:
                    await websocket.send_json({"type": "server_ping", "server_time": now})
                except Exception:
                    raise WebSocketDisconnect()
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        if player_id and player_id in room.sockets:
            try:
                await room.sockets[player_id].send_json({"type": "error", "message": str(exc)})
            except Exception:
                pass
    finally:
        if player_id:
            async with room.lock:
                if room.sockets.get(player_id) is websocket:
                    room.sockets.pop(player_id, None)
                room.speaking_ids.discard(player_id)
                if player_id in room.players:
                    room.players[player_id].connected = False
                    room.disconnected_at[player_id] = time.time()
                if not room.sockets:
                    room.expire_at = time.time() + ROOM_TTL_SECONDS
            if room.room_id in rooms:
                await broadcast_state(room)


async def handle_message(room: Room, player_id: str, msg: Dict[str, Any]) -> None:
    msg_type = msg.get("type")
    kicked_ws: Optional[WebSocket] = None

    if msg_type in {"ping", "client_pong"}:
        room.last_seen[player_id] = time.time()
        ws = room.sockets.get(player_id)
        if ws:
            try:
                await ws.send_json({"type": "pong", "server_time": datetime.now(timezone.utc).isoformat()})
            except Exception:
                pass
        return

    if msg_type in {"rtc_offer", "rtc_answer", "rtc_ice"}:
        await forward_rtc(room, player_id, msg)
        return

    strict_persist = msg_type in CRITICAL_PERSIST_EVENTS
    rollback_data: Optional[Dict[str, Any]] = None
    operation_error: Optional[str] = None

    async with room.lock:
        rollback_data = serialize_room(room)
        try:
            if msg_type == "toggle_ready":
                if room.game:
                    raise ValueError("游戏已经开始，不能修改准备状态。")
                if player_id == room.host_id:
                    raise ValueError("房主不需要准备，等待其他玩家准备后即可开始。")
                if player_id in room.ready_ids:
                    room.ready_ids.discard(player_id)
                    add_system_chat(room, f"{room.players[player_id].seat}号-{room.players[player_id].name} 取消准备。")
                else:
                    room.ready_ids.add(player_id)
                    add_system_chat(room, f"{room.players[player_id].seat}号-{room.players[player_id].name} 已准备。")

            elif msg_type == "start_game":
                require_host(room, player_id)
                count = len(room.players)
                if not 5 <= count <= 10:
                    raise ValueError("阿瓦隆必须 5-10 人才能开始。")
                if not all(p.connected for p in room.players.values()):
                    raise ValueError("有玩家离线，不能开始游戏。")
                not_ready = [pid for pid in room.players if pid != room.host_id and pid not in room.ready_ids]
                if not_ready:
                    raise ValueError(f"还有 {len(not_ready)} 名玩家未准备。")
                room.game_seq += 1
                player_order = room.player_order()
                room.game = AvalonGame(player_order=player_order, player_names=room.player_names())
                room.game.start()
                add_system_chat(room, "身份已私密分发，游戏开始。")

            elif msg_type == "select_team":
                require_game(room)
                team = msg.get("team") or []
                room.game.select_team(player_id, team)

            elif msg_type == "speaker_finished":
                require_game(room)
                force = bool(msg.get("force")) and player_id == room.game.leader_id
                room.game.speaker_finished(player_id, force=force)

            elif msg_type == "finish_free_discussion":
                require_game(room)
                require_leader(room, player_id)
                room.game.finish_free_discussion()

            elif msg_type == "team_vote":
                require_game(room)
                room.game.submit_team_vote(player_id, msg.get("vote"))

            elif msg_type == "mission_vote":
                require_game(room)
                room.game.submit_mission_vote(player_id, msg.get("vote"))

            elif msg_type == "continue_after_result":
                require_game(room)
                require_leader(room, player_id)
                room.game.continue_after_mission_result()

            elif msg_type == "assassin_target":
                require_game(room)
                room.game.submit_assassin_target(player_id, msg.get("target"))

            elif msg_type == "chat":
                handle_chat(room, player_id, msg.get("text") or "")

            elif msg_type == "speaking_state":
                if bool(msg.get("speaking")):
                    room.speaking_ids.add(player_id)
                else:
                    room.speaking_ids.discard(player_id)

            elif msg_type == "voice_ready":
                # Voice state is intentionally not persisted; LiveKit reconnects separately.
                pass

            elif msg_type == "kick_player":
                kicked_ws = kick_player(room, player_id, sanitize_id(msg.get("target") or ""))

            elif msg_type == "reset_room":
                require_host(room, player_id)
                room.game = None
                room.game_seq += 1
                room.chat_history = []
                room.ready_ids.clear()
                room.speaking_ids.clear()
                add_system_chat(room, "房间已重置，玩家可以重新开局。")

            else:
                raise ValueError("未知事件类型。")

            if strict_persist:
                saved = await save_room(room, strict=True)
                if not saved:
                    restore_room_from_data(room, rollback_data)
                    operation_error = "房间状态保存失败，本次操作未生效。请稍后重试，避免一局游戏丢失。"

        except Exception as exc:
            if rollback_data and strict_persist:
                restore_room_from_data(room, rollback_data)
            operation_error = str(exc)
            if room.game:
                room.game.set_error(str(exc))
            else:
                add_system_chat(room, f"⚠️ {exc}")

    if operation_error:
        ws = room.sockets.get(player_id)
        if ws:
            with contextlib.suppress(Exception):
                await ws.send_json({"type": "error", "message": operation_error})

    if kicked_ws and not operation_error:
        try:
            await kicked_ws.send_json({"type": "kicked", "message": "你已被房主移出圆桌。"})
            await kicked_ws.close()
        except Exception:
            pass

    await broadcast_state(room)


def kick_player(room: Room, actor_id: str, target_id: str) -> Optional[WebSocket]:
    if not target_id or target_id not in room.players:
        raise ValueError("要踢出的玩家不存在。")
    if target_id == actor_id:
        raise ValueError("不能踢出自己。")
    if room.host_id != actor_id:
        raise ValueError("只有房主可以踢人。")
    if room.game:
        raise ValueError("游戏开始后不能踢人，以免破坏身份、票数和当前轮次。请先重置房间。")
    target = room.players[target_id]
    ws = room.sockets.pop(target_id, None)
    room.players.pop(target_id, None)
    room.speaking_ids.discard(target_id)
    room.ready_ids.discard(target_id)
    # 重新压缩座位，保证显示仍为 1号、2号、3号……
    for idx, pid in enumerate(room.player_order(), start=1):
        room.players[pid].seat = idx
    add_system_chat(room, f"{target.seat}号-{target.name} 已被房主移出圆桌。")
    return ws


def handle_chat(room: Room, player_id: str, text: str) -> None:
    text = text.strip()
    if not text:
        return
    if len(text) > 500:
        raise ValueError("聊天内容过长，最多 500 字。")
    if room.game and not room.game.can_chat(player_id):
        raise ValueError("当前阶段不允许文字聊天，请等待法官开放权限。")
    add_chat(room, player_id, text)


def add_chat(room: Room, player_id: str, text: str) -> None:
    player = room.players[player_id]
    room.chat_history.append(
        {
            "type": "player",
            "player_id": player_id,
            "name": player.name,
            "seat": player.seat,
            "text": text,
            "time": datetime.now(timezone.utc).isoformat(),
        }
    )
    room.chat_history = room.chat_history[-MAX_CHAT_HISTORY:]


def add_system_chat(room: Room, text: str) -> None:
    room.chat_history.append({"type": "system", "text": text, "time": datetime.now(timezone.utc).isoformat()})
    room.chat_history = room.chat_history[-MAX_CHAT_HISTORY:]


async def safe_send_json(ws: WebSocket, payload: Dict[str, Any]) -> bool:
    try:
        await asyncio.wait_for(ws.send_json(payload), timeout=WS_SEND_TIMEOUT)
        return True
    except Exception:
        return False


async def broadcast_state(room: Room) -> None:
    await save_room(room, strict=False)
    dead: List[str] = []
    for pid, ws in list(room.sockets.items()):
        ok = await safe_send_json(ws, room.snapshot_for(pid))
        if not ok:
            dead.append(pid)
    if dead:
        async with room.lock:
            for pid in dead:
                room.sockets.pop(pid, None)
                room.speaking_ids.discard(pid)
                if pid in room.players:
                    room.players[pid].connected = False
                    room.disconnected_at[pid] = time.time()
            if not room.sockets:
                room.expire_at = time.time() + ROOM_TTL_SECONDS
        await save_room(room, strict=False)


async def forward_rtc(room: Room, sender_id: str, msg: Dict[str, Any]) -> None:
    target = msg.get("target")
    if not target or target not in room.sockets:
        return
    payload = {
        "type": msg.get("type"),
        "sender": sender_id,
        "payload": msg.get("payload"),
    }
    try:
        await asyncio.wait_for(room.sockets[target].send_json(payload), timeout=WS_SEND_TIMEOUT)
    except Exception:
        pass



def redis_key(room_id: str) -> str:
    return f"avalon:room:{room_id}"


def serialize_room(room: Room) -> Dict[str, Any]:
    return {
        "room_id": room.room_id,
        "host_id": room.host_id,
        "players": {pid: {"id": p.id, "name": p.name, "seat": p.seat, "connected": p.connected} for pid, p in room.players.items()},
        "ready_ids": list(room.ready_ids),
        "game": room.game.to_dict() if room.game else None,
        "chat_history": room.chat_history[-MAX_CHAT_HISTORY:],
        "game_seq": room.game_seq,
        "updated_at": time.time(),
    }


def deserialize_room(data: Dict[str, Any]) -> Room:
    room_id = normalize_room(data.get("room_id") or "")
    room = Room(room_id=room_id)
    room.host_id = data.get("host_id")
    room.players = {
        pid: PlayerRecord(
            id=p.get("id") or pid,
            name=sanitize_name(p.get("name") or "玩家"),
            seat=int(p.get("seat") or 1),
            connected=False,
        )
        for pid, p in (data.get("players") or {}).items()
    }
    room.ready_ids = set(data.get("ready_ids") or [])
    room.game = AvalonGame.from_dict(data["game"]) if data.get("game") else None
    room.chat_history = list(data.get("chat_history") or [])[-MAX_CHAT_HISTORY:]
    room.game_seq = int(data.get("game_seq") or 0)
    return room


def restore_room_from_data(room: Room, data: Dict[str, Any]) -> None:
    """Rollback room state while preserving live socket/lock fields."""
    restored = deserialize_room(data)
    live_sockets = room.sockets
    live_last_seen = room.last_seen
    live_disconnected_at = room.disconnected_at
    live_expire_at = room.expire_at
    live_speaking = set(room.speaking_ids)

    room.host_id = restored.host_id
    room.players = restored.players
    room.game = restored.game
    room.chat_history = restored.chat_history
    room.ready_ids = restored.ready_ids
    room.game_seq = restored.game_seq

    room.sockets = live_sockets
    room.last_seen = live_last_seen
    room.disconnected_at = live_disconnected_at
    room.expire_at = live_expire_at
    room.speaking_ids = live_speaking.intersection(room.players.keys())


def persistence_configured() -> bool:
    return bool(redis_rest_configured() or os.getenv("REDIS_URL"))


def _redis_rest_command_sync(command: List[Any]) -> Any:
    url = (os.getenv("UPSTASH_REDIS_REST_URL") or "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN") or ""
    if not url or not token:
        raise RuntimeError("Upstash REST is not configured")
    body = json.dumps(command, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=REDIS_OPERATION_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    if isinstance(payload, dict) and payload.get("error"):
        raise RuntimeError(payload["error"])
    return payload.get("result") if isinstance(payload, dict) else payload


async def redis_rest_command(command: List[Any]) -> Any:
    return await asyncio.to_thread(_redis_rest_command_sync, command)



async def load_room_from_redis(room_id: str) -> Optional[Room]:
    key = redis_key(room_id)
    raw: Optional[str] = None
    had_error = False

    if redis_rest_configured():
        try:
            raw = await redis_rest_command(["GET", key])
        except Exception as exc:
            had_error = True
            print(f"[redis] REST load room {room_id} failed: {exc}")

    if raw is None:
        client = await get_redis_client()
        if client:
            for attempt in range(REDIS_SAVE_RETRIES + 1):
                try:
                    raw = await client.get(key)
                    break
                except Exception as exc:
                    had_error = True
                    print(f"[redis] TCP load room {room_id} failed attempt {attempt + 1}: {exc}")
                    client = await reset_redis_client()

    # Important: when Redis is configured but unreachable, do NOT create a fresh empty room.
    # Otherwise Render restart + temporary Redis failure can overwrite/lose an active game.
    if raw is None and had_error and persistence_configured():
        raise RedisPersistenceError(f"无法从 Redis 恢复房间 {room_id}")

    if not raw:
        return None

    try:
        data = json.loads(raw)
        room = deserialize_room(data)
        rooms[room_id] = room
        return room
    except Exception as exc:
        print(f"[redis] deserialize room {room_id} failed: {exc}")
        raise RedisPersistenceError(f"房间 {room_id} 的 Redis 数据损坏或无法反序列化")


async def save_room(room: Room, *, strict: bool = False) -> bool:
    """Persist a room. If strict=True and persistence is configured, failure means the action must not advance."""
    if not persistence_configured():
        return True  # local development mode

    key = redis_key(room.room_id)
    payload = json.dumps(serialize_room(room), ensure_ascii=False)

    if redis_rest_configured():
        for attempt in range(REDIS_SAVE_RETRIES + 1):
            try:
                await redis_rest_command(["SETEX", key, ROOM_PERSIST_TTL_SECONDS, payload])
                return True
            except Exception as exc:
                print(f"[redis] REST save room {room.room_id} failed attempt {attempt + 1}: {exc}")

    client = await get_redis_client()
    if client:
        for attempt in range(REDIS_SAVE_RETRIES + 1):
            try:
                await client.setex(key, ROOM_PERSIST_TTL_SECONDS, payload)
                return True
            except Exception as exc:
                print(f"[redis] TCP save room {room.room_id} failed attempt {attempt + 1}: {exc}")
                client = await reset_redis_client()

    if strict:
        print(f"[redis] STRICT save room {room.room_id} failed; operation rolled back")
    return False


async def delete_room_from_redis(room_id: str) -> None:
    key = redis_key(room_id)
    if redis_rest_configured():
        with contextlib.suppress(Exception):
            await redis_rest_command(["DEL", key])
            return
    client = await get_redis_client()
    if client:
        with contextlib.suppress(Exception):
            await client.delete(key)


async def get_room(room_id: str, create: bool = False) -> Optional[Room]:
    room_id = normalize_room(room_id)
    room = rooms.get(room_id)
    if room:
        return room

    try:
        room = await load_room_from_redis(room_id)
    except RedisPersistenceError as exc:
        print(f"[redis] get room {room_id} blocked: {exc}")
        return None

    if room:
        return room
    if create:
        room = Room(room_id=room_id)
        rooms[room_id] = room
        return room
    return None


async def room_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(30)
        now = time.time()
        for room_id, room in list(rooms.items()):
            async with room.lock:
                if room.sockets:
                    room.expire_at = None
                    continue
                if not room.expire_at:
                    room.expire_at = now + ROOM_TTL_SECONDS
                if room.expire_at and now >= room.expire_at:
                    rooms.pop(room_id, None)


def require_game(room: Room) -> None:
    if not room.game:
        raise ValueError("游戏尚未开始。")


def require_host(room: Room, player_id: str) -> None:
    if room.host_id != player_id:
        raise ValueError("只有房主可以执行该操作。")


def require_leader(room: Room, player_id: str) -> None:
    require_game(room)
    if not room.game or room.game.leader_id != player_id:
        raise ValueError("只有本轮队长可以执行该操作。")


def next_available_seat(room: Room) -> int:
    used = {p.seat for p in room.players.values()}
    for seat in range(1, 11):
        if seat not in used:
            return seat
    raise ValueError("房间已满。")


def normalize_room(room_id: str) -> str:
    raw = (room_id or "").upper().strip()
    allowed = string.ascii_uppercase + string.digits + "-_"
    cleaned = "".join(ch for ch in raw if ch in allowed)
    return cleaned[:24] or random_room_code()


def random_room_code() -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(random.choice(alphabet) for _ in range(6))


def sanitize_name(name: str) -> str:
    name = " ".join(name.strip().split())
    return name[:24] or "玩家"


def sanitize_id(player_id: str) -> str:
    allowed = string.ascii_letters + string.digits + "-_"
    return "".join(ch for ch in player_id if ch in allowed)[:80]


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
