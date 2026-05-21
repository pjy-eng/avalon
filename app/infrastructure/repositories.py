from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application.events import AppEvent
from app.infrastructure.db import EventRecord, GameRecord, ParticipantRecord, RoomRecord


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


class RoomRepository:
    def __init__(self, session: Session):
        self.session = session

    def upsert_room(self, room_id: str, ruleset: str, status: str) -> None:
        record = self.session.get(RoomRecord, room_id)
        if record is None:
            self.session.add(RoomRecord(room_id=room_id, ruleset=ruleset, status=status))
            return

        record.ruleset = ruleset
        record.status = status

    def upsert_participant(
        self,
        room_id: str,
        player_id: str,
        nickname: str,
        seat: int,
        participant_type: str,
        token_version: int,
    ) -> None:
        participant_id = self._participant_id(room_id, player_id)
        record = self.session.get(ParticipantRecord, participant_id)
        if record is None:
            self.session.add(
                ParticipantRecord(
                    participant_id=participant_id,
                    room_id=room_id,
                    player_id=player_id,
                    nickname=nickname,
                    seat=seat,
                    participant_type=participant_type,
                    token_version=token_version,
                )
            )
            return

        record.nickname = nickname
        record.seat = seat
        record.participant_type = participant_type
        record.token_version = token_version

    def upsert_game(self, room_id: str, phase: str, state: dict) -> None:
        record = self.session.get(GameRecord, room_id)
        if record is None:
            self.session.add(GameRecord(room_id=room_id, phase=phase, state=state))
            return

        record.phase = phase
        record.state = state

    def get_room_bundle(self, room_id: str) -> dict:
        room = self.session.get(RoomRecord, room_id)
        participants = self.session.scalars(
            select(ParticipantRecord)
            .where(ParticipantRecord.room_id == room_id)
            .order_by(ParticipantRecord.seat, ParticipantRecord.player_id)
        ).all()
        game = self.session.get(GameRecord, room_id)

        return {
            "room": self._room_to_dict(room),
            "participants": [
                self._participant_to_dict(participant) for participant in participants
            ],
            "game": self._game_to_dict(game),
        }

    @staticmethod
    def _participant_id(room_id: str, player_id: str) -> str:
        return f"{room_id}:{player_id}"

    @staticmethod
    def _room_to_dict(record: RoomRecord | None) -> dict | None:
        if record is None:
            return None
        return {
            "room_id": record.room_id,
            "ruleset": record.ruleset,
            "status": record.status,
        }

    @staticmethod
    def _participant_to_dict(record: ParticipantRecord) -> dict:
        return {
            "participant_id": record.participant_id,
            "room_id": record.room_id,
            "player_id": record.player_id,
            "nickname": record.nickname,
            "seat": record.seat,
            "participant_type": record.participant_type,
            "token_version": record.token_version,
        }

    @staticmethod
    def _game_to_dict(record: GameRecord | None) -> dict | None:
        if record is None:
            return None
        return {
            "room_id": record.room_id,
            "phase": record.phase,
            "state": record.state,
        }
