import pytest

from app.realtime import ConnectionManager


class FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_broadcast_room_sends_to_all_connections_for_same_player():
    manager = ConnectionManager()
    first = FakeWebSocket()
    second = FakeWebSocket()
    manager.connect("ROOM1", "p1", first)
    manager.connect("ROOM1", "p1", second)

    await manager.broadcast_room("ROOM1", payload={"type": "state", "seq": 1})

    assert first.sent == [{"type": "state", "seq": 1}]
    assert second.sent == [{"type": "state", "seq": 1}]
    assert manager.online_counts("ROOM1") == {"p1": 2}
