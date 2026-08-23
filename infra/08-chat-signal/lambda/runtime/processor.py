"""Schema validation, event-time aggregation, and Candidate creation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
import secrets
from typing import Any, Callable

from classifier import classify
from repository import (
    EVENT_TTL_SECONDS,
    WINDOW_TTL_SECONDS,
    StateRepository,
)


WINDOW_SECONDS = 15
LATE_ALLOWANCE_SECONDS = 5
COOLDOWN_SECONDS = 60
CANDIDATE_TYPE = "USER_PERCEIVED_LATENCY"

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ULID_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
_BROADCAST_PATTERN = re.compile(r"^bc_[0-9]+$")
_USER_KEY_PATTERN = re.compile(r"^u_[0-9a-f]{16}$")


class SchemaRejected(ValueError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


@dataclass(frozen=True)
class ChatSignal:
    event_id: str
    event_ts: datetime
    broadcast_id: str
    user_key: str
    message: str


def _encode_base32(value: int, length: int) -> str:
    output = []
    for _ in range(length):
        output.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(output))


def new_candidate_id(now: datetime) -> str:
    timestamp_ms = int(now.timestamp() * 1000)
    random_bits = int.from_bytes(secrets.token_bytes(10), "big")
    return f"cand_{_encode_base32(timestamp_ms, 10)}{_encode_base32(random_bits, 16)}"


def _parse_event_ts(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SchemaRejected("EVENT_TS_INVALID") from error
    if parsed.tzinfo is None:
        raise SchemaRejected("EVENT_TS_TIMEZONE_REQUIRED")
    return parsed.astimezone(timezone.utc)


def parse_signal(body: str) -> ChatSignal:
    try:
        payload = json.loads(body)
    except (json.JSONDecodeError, TypeError) as error:
        raise SchemaRejected("BODY_NOT_JSON") from error
    if not isinstance(payload, dict):
        raise SchemaRejected("BODY_NOT_OBJECT")

    if payload.get("schema_version") != "1.0":
        raise SchemaRejected("SCHEMA_VERSION_UNSUPPORTED")

    required_strings = ("event_id", "event_ts", "broadcast_id", "user_key", "message")
    for field in required_strings:
        if not isinstance(payload.get(field), str):
            raise SchemaRejected(f"{field.upper()}_INVALID")

    event_id = payload["event_id"]
    broadcast_id = payload["broadcast_id"]
    user_key = payload["user_key"]
    message = payload["message"]
    trace_id = payload.get("trace_id")

    if not _ULID_PATTERN.fullmatch(event_id):
        raise SchemaRejected("EVENT_ID_INVALID")
    if not _BROADCAST_PATTERN.fullmatch(broadcast_id):
        raise SchemaRejected("BROADCAST_ID_INVALID")
    if not _USER_KEY_PATTERN.fullmatch(user_key):
        raise SchemaRejected("USER_KEY_INVALID")
    if len(message) > 200:
        raise SchemaRejected("MESSAGE_TOO_LONG")
    if trace_id is not None and (not isinstance(trace_id, str) or len(trace_id) > 128):
        raise SchemaRejected("TRACE_ID_INVALID")

    return ChatSignal(
        event_id=event_id,
        event_ts=_parse_event_ts(payload["event_ts"]),
        broadcast_id=broadcast_id,
        user_key=user_key,
        message=message,
    )


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _window_bounds(event_ts: datetime) -> tuple[datetime, datetime]:
    epoch = int(event_ts.timestamp())
    start_epoch = epoch - (epoch % WINDOW_SECONDS)
    start = datetime.fromtimestamp(start_epoch, tz=timezone.utc)
    return start, start + timedelta(seconds=WINDOW_SECONDS)


def _qualifies(window: dict[str, Any]) -> bool:
    matched = int(window["matched_messages"])
    users = int(window["unique_users"])
    strong = int(window["strong_signal_count"])
    weak = int(window["weak_signal_count"])
    rule_a = strong >= 1 and matched >= 4 and users >= 3
    rule_b = strong == 0 and weak >= 4 and users >= 4
    return rule_a or rule_b


class ChatSignalProcessor:
    def __init__(
        self,
        repository: StateRepository,
        *,
        candidate_id: Callable[[datetime], str] = new_candidate_id,
    ) -> None:
        self._repository = repository
        self._candidate_id = candidate_id

    def process_body(self, body: str, *, now: datetime | None = None) -> dict[str, Any]:
        received_at = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        signal = parse_signal(body)
        now_epoch = int(received_at.timestamp())

        if not self._repository.claim_event(
            signal.event_id, now_epoch + EVENT_TTL_SECONDS
        ):
            return {"status": "DUPLICATE_EVENT"}

        window_start, window_end = _window_bounds(signal.event_ts)
        if received_at > window_end + timedelta(seconds=LATE_ALLOWANCE_SECONDS):
            self._repository.complete_event(signal.event_id)
            return {"status": "LATE_EVENT_DROPPED"}

        classification = classify(signal.message)
        if not classification.matched:
            self._repository.complete_event(signal.event_id)
            return {"status": "UNRELATED"}

        window_key = (
            f"WINDOW#{signal.broadcast_id}#{CANDIDATE_TYPE}#{_iso(window_start)}"
        )
        added = self._repository.add_vote(
            window_key=window_key,
            user_key=signal.user_key,
            strength=classification.strength,
            surface=classification.surface,
            rule_ids=classification.rule_ids,
            window_start=_iso(window_start),
            window_end=_iso(window_end),
            expires_at=now_epoch + WINDOW_TTL_SECONDS,
        )
        window = self._repository.get_window(window_key)
        if not _qualifies(window):
            self._repository.complete_event(signal.event_id)
            return {
                "status": "BELOW_THRESHOLD" if added else "DUPLICATE_USER_VOTE"
            }

        candidate, created = self._repository.record_candidate(
            proposed_candidate_id=self._candidate_id(received_at),
            broadcast_id=signal.broadcast_id,
            candidate_type=CANDIDATE_TYPE,
            snapshot=window,
            created_at=_iso(received_at),
            now_epoch=now_epoch,
            cooldown_seconds=COOLDOWN_SECONDS,
        )
        self._repository.complete_event(signal.event_id)
        return {
            "status": (
                "CANDIDATE_CREATED"
                if created
                else "CANDIDATE_UPDATED" if added else "DUPLICATE_USER_VOTE"
            ),
            "candidate_id": candidate["candidate_id"],
        }
