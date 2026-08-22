"""Fail-safe Phase 1B skeleton for the Chat Signal SQS consumer.

The skeleton deliberately does not read SQS bodies. It reports every record as
failed so an accidental invocation cannot acknowledge raw chat before the real
processor and its acceptance tests exist.
"""

import logging
from typing import Any


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)


def handler(event: dict[str, Any], _context: Any) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records", []) if isinstance(event, dict) else []
    message_ids: list[str] = []

    for record in records:
        message_id = record.get("messageId") if isinstance(record, dict) else None
        if not isinstance(message_id, str) or not message_id:
            LOGGER.error(
                "chat_signal_worker_skeleton_invalid_envelope record_count=%d",
                len(records),
            )
            raise RuntimeError("CHAT_SIGNAL_SQS_MESSAGE_ID_MISSING")
        message_ids.append(message_id)

    LOGGER.warning(
        "chat_signal_worker_skeleton_disabled record_count=%d",
        len(message_ids),
    )
    return {
        "batchItemFailures": [
            {"itemIdentifier": message_id}
            for message_id in message_ids
        ]
    }
