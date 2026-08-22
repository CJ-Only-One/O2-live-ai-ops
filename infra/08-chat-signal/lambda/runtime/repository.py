"""DynamoDB-backed authoritative state for chat incident candidates."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Protocol


EVENT_TTL_SECONDS = 10 * 60
WINDOW_TTL_SECONDS = 10 * 60
CANDIDATE_TTL_SECONDS = 7 * 24 * 60 * 60


class RepositoryError(RuntimeError):
    """A retryable state-store failure with a content-free error code."""


class StateRepository(Protocol):
    def claim_event(self, event_id: str, expires_at: int) -> bool: ...

    def complete_event(self, event_id: str) -> None: ...

    def add_vote(
        self,
        *,
        window_key: str,
        user_key: str,
        strength: str,
        surface: str,
        rule_ids: tuple[str, ...],
        window_start: str,
        window_end: str,
        expires_at: int,
    ) -> bool: ...

    def get_window(self, window_key: str) -> dict[str, Any]: ...

    def record_candidate(
        self,
        *,
        proposed_candidate_id: str,
        broadcast_id: str,
        candidate_type: str,
        snapshot: dict[str, Any],
        created_at: str,
        now_epoch: int,
        cooldown_seconds: int,
    ) -> tuple[dict[str, Any], bool]: ...


def _empty_window(window_start: str, window_end: str) -> dict[str, Any]:
    return {
        "window_start": window_start,
        "window_end": window_end,
        "matched_messages": 0,
        "unique_users": 0,
        "strong_signal_count": 0,
        "weak_signal_count": 0,
        "matched_rule_ids": [],
        "surface_counts": {"READ_PATH": 0, "PLAYBACK": 0, "CHAT": 0},
    }


def _candidate_payload(
    *,
    candidate_id: str,
    broadcast_id: str,
    candidate_type: str,
    snapshots: dict[str, dict[str, Any]],
    created_at: str,
) -> dict[str, Any]:
    ordered = [snapshots[key] for key in sorted(snapshots)]
    strong_count = sum(int(item["strong_signal_count"]) for item in ordered)
    weak_count = sum(int(item["weak_signal_count"]) for item in ordered)
    surface_counts = {
        surface: sum(int(item["surface_counts"].get(surface, 0)) for item in ordered)
        for surface in ("READ_PATH", "PLAYBACK", "CHAT")
    }
    priority = {"READ_PATH": 3, "PLAYBACK": 2, "CHAT": 1}
    suspected_surface = "UNKNOWN"
    if strong_count:
        suspected_surface = max(
            surface_counts,
            key=lambda value: (surface_counts[value], priority[value]),
        )

    return {
        "schema_version": "1.0",
        "candidate_id": candidate_id,
        "candidate_type": candidate_type,
        "broadcast_id": broadcast_id,
        "suspected_surface": suspected_surface,
        "confidence": "MEDIUM" if strong_count else "LOW",
        "window_start": min(item["window_start"] for item in ordered),
        "window_end": max(item["window_end"] for item in ordered),
        "matched_messages": sum(int(item["matched_messages"]) for item in ordered),
        "unique_users": sum(int(item["unique_users"]) for item in ordered),
        "strong_signal_count": strong_count,
        "weak_signal_count": weak_count,
        "matched_rule_ids": sorted(
            {rule_id for item in ordered for rule_id in item["matched_rule_ids"]}
        ),
        "metric_status": "NOT_CHECKED",
        "root_cause": "UNDETERMINED",
        "requires_metric_corroboration": True,
        "raw_chat_included": False,
        "agent_handoff_status": "NOT_CONFIGURED",
        "created_at": created_at,
    }


@dataclass
class _ActiveCandidate:
    candidate_id: str
    cooldown_until: int


class InMemoryRepository:
    """Behavioral test repository using the same keys and merge rules as DynamoDB."""

    def __init__(self) -> None:
        self.events: dict[str, str] = {}
        self.windows: dict[str, dict[str, Any]] = {}
        self.user_votes: set[tuple[str, str]] = set()
        self.candidates: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, dict[str, dict[str, Any]]] = {}
        self.active: dict[tuple[str, str], _ActiveCandidate] = {}

    def claim_event(self, event_id: str, _expires_at: int) -> bool:
        if self.events.get(event_id) == "COMPLETED":
            return False
        self.events[event_id] = "PENDING"
        return True

    def complete_event(self, event_id: str) -> None:
        self.events[event_id] = "COMPLETED"

    def add_vote(
        self,
        *,
        window_key: str,
        user_key: str,
        strength: str,
        surface: str,
        rule_ids: tuple[str, ...],
        window_start: str,
        window_end: str,
        expires_at: int,
    ) -> bool:
        del expires_at
        vote_key = (window_key, user_key)
        if vote_key in self.user_votes:
            return False
        self.user_votes.add(vote_key)
        window = self.windows.setdefault(window_key, _empty_window(window_start, window_end))
        window["matched_messages"] += 1
        window["unique_users"] += 1
        window["strong_signal_count"] += int(strength == "STRONG")
        window["weak_signal_count"] += int(strength == "WEAK")
        if strength == "STRONG":
            window["surface_counts"][surface] += 1
        window["matched_rule_ids"] = sorted(
            set(window["matched_rule_ids"]).union(rule_ids)
        )
        return True

    def get_window(self, window_key: str) -> dict[str, Any]:
        return deepcopy(self.windows[window_key])

    def record_candidate(
        self,
        *,
        proposed_candidate_id: str,
        broadcast_id: str,
        candidate_type: str,
        snapshot: dict[str, Any],
        created_at: str,
        now_epoch: int,
        cooldown_seconds: int,
    ) -> tuple[dict[str, Any], bool]:
        active_key = (broadcast_id, candidate_type)
        active = self.active.get(active_key)
        created = active is None or active.cooldown_until <= now_epoch
        if created:
            candidate_id = proposed_candidate_id
            active = _ActiveCandidate(candidate_id, now_epoch + cooldown_seconds)
            self.active[active_key] = active
            self.snapshots[candidate_id] = {}
        else:
            candidate_id = active.candidate_id

        self.snapshots[candidate_id][snapshot["window_start"]] = deepcopy(snapshot)
        original_created_at = self.candidates.get(candidate_id, {}).get(
            "created_at", created_at
        )
        payload = _candidate_payload(
            candidate_id=candidate_id,
            broadcast_id=broadcast_id,
            candidate_type=candidate_type,
            snapshots=self.snapshots[candidate_id],
            created_at=original_created_at,
        )
        self.candidates[candidate_id] = payload
        return deepcopy(payload), created


def _is_conditional_failure(error: Exception) -> bool:
    response = getattr(error, "response", {})
    code = response.get("Error", {}).get("Code") if isinstance(response, dict) else None
    return code in {"ConditionalCheckFailedException", "TransactionCanceledException"}


class DynamoRepository:
    """Production repository. The Lambda runtime supplies boto3."""

    def __init__(
        self,
        table_name: str,
        *,
        client: Any | None = None,
        serializer: Any | None = None,
        deserializer: Any | None = None,
    ) -> None:
        if client is None or serializer is None or deserializer is None:
            import boto3
            from boto3.dynamodb.types import TypeDeserializer, TypeSerializer

            client = client or boto3.client("dynamodb")
            serializer = serializer or TypeSerializer()
            deserializer = deserializer or TypeDeserializer()
        self._table_name = table_name
        self._client = client
        self._serializer = serializer
        self._deserializer = deserializer

    def _values(self, values: dict[str, Any]) -> dict[str, Any]:
        return {key: self._serializer.serialize(value) for key, value in values.items()}

    def _item(self, item: dict[str, Any]) -> dict[str, Any]:
        return self._values(item)

    def _decode_item(self, item: dict[str, Any]) -> dict[str, Any]:
        return {key: self._deserializer.deserialize(value) for key, value in item.items()}

    def _get(self, pk: str, sk: str) -> dict[str, Any] | None:
        try:
            response = self._client.get_item(
                TableName=self._table_name,
                Key=self._item({"pk": pk, "sk": sk}),
                ConsistentRead=True,
            )
        except Exception as error:
            raise RepositoryError("DDB_GET_FAILED") from error
        item = response.get("Item")
        return self._decode_item(item) if item else None

    def claim_event(self, event_id: str, expires_at: int) -> bool:
        event_pk = f"EVENT#{event_id}"
        try:
            self._client.put_item(
                TableName=self._table_name,
                Item=self._item(
                    {
                        "pk": event_pk,
                        "sk": "META",
                        "status": "PENDING",
                        "expires_at": expires_at,
                    }
                ),
                ConditionExpression="attribute_not_exists(pk)",
            )
            return True
        except Exception as error:
            if _is_conditional_failure(error):
                existing = self._get(event_pk, "META")
                return existing is not None and existing.get("status") != "COMPLETED"
            raise RepositoryError("DDB_EVENT_CLAIM_FAILED") from error

    def complete_event(self, event_id: str) -> None:
        try:
            self._client.update_item(
                TableName=self._table_name,
                Key=self._item({"pk": f"EVENT#{event_id}", "sk": "META"}),
                UpdateExpression="SET #status = :completed",
                ConditionExpression="attribute_exists(pk)",
                ExpressionAttributeNames={"#status": "status"},
                ExpressionAttributeValues=self._values({":completed": "COMPLETED"}),
            )
        except Exception as error:
            raise RepositoryError("DDB_EVENT_COMPLETE_FAILED") from error

    def add_vote(
        self,
        *,
        window_key: str,
        user_key: str,
        strength: str,
        surface: str,
        rule_ids: tuple[str, ...],
        window_start: str,
        window_end: str,
        expires_at: int,
    ) -> bool:
        surface_attr = {
            "READ_PATH": "surface_read_path",
            "PLAYBACK": "surface_playback",
            "CHAT": "surface_chat",
            "UNKNOWN": "surface_unknown",
        }[surface]
        values = self._values(
            {
                ":one": 1,
                ":strong": int(strength == "STRONG"),
                ":weak": int(strength == "WEAK"),
                ":surface": int(strength == "STRONG"),
                ":rules": set(rule_ids),
                ":window_start": window_start,
                ":window_end": window_end,
                ":expires_at": expires_at,
            }
        )
        try:
            self._client.transact_write_items(
                TransactItems=[
                    {
                        "Put": {
                            "TableName": self._table_name,
                            "Item": self._item(
                                {
                                    "pk": window_key,
                                    "sk": f"USER#{user_key}",
                                    "expires_at": expires_at,
                                }
                            ),
                            "ConditionExpression": "attribute_not_exists(pk)",
                        }
                    },
                    {
                        "Update": {
                            "TableName": self._table_name,
                            "Key": self._item({"pk": window_key, "sk": "AGG"}),
                            "UpdateExpression": (
                                "SET window_start = :window_start, window_end = :window_end, "
                                "expires_at = :expires_at "
                                "ADD matched_messages :one, unique_users :one, "
                                "strong_signal_count :strong, weak_signal_count :weak, "
                                f"{surface_attr} :surface, matched_rule_ids :rules"
                            ),
                            "ExpressionAttributeValues": values,
                        }
                    },
                ]
            )
            return True
        except Exception as error:
            if _is_conditional_failure(error):
                existing_vote = self._get(window_key, f"USER#{user_key}")
                if existing_vote is not None:
                    return False
            raise RepositoryError("DDB_WINDOW_VOTE_FAILED") from error

    def get_window(self, window_key: str) -> dict[str, Any]:
        item = self._get(window_key, "AGG")
        if item is None:
            raise RepositoryError("DDB_WINDOW_MISSING")
        return {
            "window_start": item["window_start"],
            "window_end": item["window_end"],
            "matched_messages": int(item.get("matched_messages", 0)),
            "unique_users": int(item.get("unique_users", 0)),
            "strong_signal_count": int(item.get("strong_signal_count", 0)),
            "weak_signal_count": int(item.get("weak_signal_count", 0)),
            "matched_rule_ids": sorted(item.get("matched_rule_ids", set())),
            "surface_counts": {
                "READ_PATH": int(item.get("surface_read_path", 0)),
                "PLAYBACK": int(item.get("surface_playback", 0)),
                "CHAT": int(item.get("surface_chat", 0)),
            },
        }

    def record_candidate(
        self,
        *,
        proposed_candidate_id: str,
        broadcast_id: str,
        candidate_type: str,
        snapshot: dict[str, Any],
        created_at: str,
        now_epoch: int,
        cooldown_seconds: int,
    ) -> tuple[dict[str, Any], bool]:
        guard_pk = f"ACTIVE#{broadcast_id}#{candidate_type}"
        for _attempt in range(4):
            guard = self._get(guard_pk, "META")
            if guard and int(guard["cooldown_until"]) > now_epoch:
                candidate_id = str(guard["candidate_id"])
                current = self._get(f"CANDIDATE#{candidate_id}", "META")
                if current is None:
                    raise RepositoryError("DDB_ACTIVE_CANDIDATE_MISSING")
                snapshots = dict(current.get("window_snapshots", {}))
                snapshots[snapshot["window_start"]] = deepcopy(snapshot)
                payload = _candidate_payload(
                    candidate_id=candidate_id,
                    broadcast_id=broadcast_id,
                    candidate_type=candidate_type,
                    snapshots=snapshots,
                    created_at=str(current["payload"]["created_at"]),
                )
                version = int(current.get("version", 1))
                replacement = {
                    **current,
                    "window_snapshots": snapshots,
                    "payload": payload,
                    "version": version + 1,
                }
                try:
                    self._client.put_item(
                        TableName=self._table_name,
                        Item=self._item(replacement),
                        ConditionExpression="version = :version",
                        ExpressionAttributeValues=self._values({":version": version}),
                    )
                    return payload, False
                except Exception as error:
                    if _is_conditional_failure(error):
                        continue
                    raise RepositoryError("DDB_CANDIDATE_UPDATE_FAILED") from error

            candidate_id = proposed_candidate_id
            snapshots = {snapshot["window_start"]: deepcopy(snapshot)}
            payload = _candidate_payload(
                candidate_id=candidate_id,
                broadcast_id=broadcast_id,
                candidate_type=candidate_type,
                snapshots=snapshots,
                created_at=created_at,
            )
            candidate_item = {
                "pk": f"CANDIDATE#{candidate_id}",
                "sk": "META",
                "payload": payload,
                "window_snapshots": snapshots,
                "version": 1,
                "expires_at": now_epoch + CANDIDATE_TTL_SECONDS,
            }
            guard_item = {
                "pk": guard_pk,
                "sk": "META",
                "candidate_id": candidate_id,
                "cooldown_until": now_epoch + cooldown_seconds,
                "expires_at": now_epoch + CANDIDATE_TTL_SECONDS,
            }
            try:
                self._client.transact_write_items(
                    TransactItems=[
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": self._item(candidate_item),
                                "ConditionExpression": "attribute_not_exists(pk)",
                            }
                        },
                        {
                            "Put": {
                                "TableName": self._table_name,
                                "Item": self._item(guard_item),
                                "ConditionExpression": (
                                    "attribute_not_exists(pk) OR cooldown_until <= :now"
                                ),
                                "ExpressionAttributeValues": self._values({":now": now_epoch}),
                            }
                        },
                    ]
                )
                return payload, True
            except Exception as error:
                if _is_conditional_failure(error):
                    continue
                raise RepositoryError("DDB_CANDIDATE_CREATE_FAILED") from error
        raise RepositoryError("DDB_CANDIDATE_CONFLICT_RETRY_EXHAUSTED")
