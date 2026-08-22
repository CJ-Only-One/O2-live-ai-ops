"""SQS partial-batch handler with content-free logs and failure records."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from processor import ChatSignalProcessor, SchemaRejected
from repository import DynamoRepository, RepositoryError


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

_PROCESSOR: ChatSignalProcessor | None = None


def _safe_error_code(error: Exception) -> str:
    value = str(error)
    return value if re.fullmatch(r"[A-Z0-9_]{1,64}", value) else "REPOSITORY_FAILURE"


def _runtime_processor() -> ChatSignalProcessor:
    global _PROCESSOR
    if _PROCESSOR is not None:
        return _PROCESSOR
    table_name = os.environ.get("CHAT_INCIDENT_TABLE_NAME", "")
    if not table_name:
        raise RepositoryError("CONFIG_TABLE_NAME_MISSING")
    _PROCESSOR = ChatSignalProcessor(DynamoRepository(table_name))
    return _PROCESSOR


def handler(
    event: dict[str, Any],
    _context: Any,
    *,
    processor: ChatSignalProcessor | None = None,
) -> dict[str, list[dict[str, str]]]:
    records = event.get("Records", []) if isinstance(event, dict) else []
    if not isinstance(records, list):
        raise RuntimeError("CHAT_SIGNAL_SQS_RECORDS_INVALID")

    failures: list[dict[str, str]] = []
    active_processor = processor

    for record in records:
        message_id = record.get("messageId") if isinstance(record, dict) else None
        if not isinstance(message_id, str) or not message_id:
            LOGGER.error(
                "chat_signal_invalid_envelope error_code=MESSAGE_ID_MISSING record_count=%d",
                len(records),
            )
            raise RuntimeError("CHAT_SIGNAL_SQS_MESSAGE_ID_MISSING")

        body = record.get("body") if isinstance(record, dict) else None
        try:
            active_processor = active_processor or _runtime_processor()
            result = active_processor.process_body(body)
            LOGGER.info(
                "chat_signal_processed message_id=%s status=%s",
                message_id,
                result["status"],
            )
        except SchemaRejected as error:
            # Invalid input is acknowledged and deleted. Only the stable code is logged.
            LOGGER.warning(
                "chat_signal_schema_rejected message_id=%s error_code=%s",
                message_id,
                error.error_code,
            )
        except RepositoryError as error:
            LOGGER.error(
                "chat_signal_retryable_failure message_id=%s error_code=%s",
                message_id,
                _safe_error_code(error),
            )
            failures.append({"itemIdentifier": message_id})
        except Exception:
            # Exception messages and tracebacks may contain the SQS body. Never render them.
            LOGGER.error(
                "chat_signal_unexpected_failure message_id=%s error_code=UNEXPECTED",
                message_id,
            )
            failures.append({"itemIdentifier": message_id})

    return {"batchItemFailures": failures}
