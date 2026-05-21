from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import AppEvent
from app.infrastructure.db import EventRecord


class EventRepository:
    def __init__(self, session: Session):
        self.session = session

    def append(self, event: AppEvent) -> None:
        self.session.add(
            EventRecord(
                event_id=event.event_id,
                event_type=event.event_type,
                room_id=event.room_id,
                actor_id=event.actor_id,
                request_id=event.request_id,
                payload=event.payload,
                created_at=event.created_at,
            )
        )

    def list_room_events(self, room_id: str) -> list[AppEvent]:
        records = self.session.scalars(
            select(EventRecord)
            .where(EventRecord.room_id == room_id)
            .order_by(EventRecord.record_id, EventRecord.event_id)
        ).all()

        return [
            AppEvent(
                event_type=record.event_type,
                room_id=record.room_id,
                actor_id=record.actor_id,
                payload=record.payload,
                request_id=record.request_id,
                event_id=record.event_id,
                created_at=record.created_at,
            )
            for record in records
        ]
