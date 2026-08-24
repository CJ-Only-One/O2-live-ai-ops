"""SQS partial-batch handler with content-free logs and failure records."""

from __future__ import annotations

import logging
import os
import re
import json
import time
from typing import Any

from processor import ChatSignalProcessor, SchemaRejected
from repository import DynamoRepository, RepositoryError


LOGGER = logging.getLogger()
LOGGER.setLevel(logging.INFO)

_PROCESSOR: ChatSignalProcessor | None = None
_COLD_START = True


def _emit_metrics(*, batch_size: int, success: int, retry: int, rejected: int, duration_ms: float) -> None:
    payload = {
        "_aws": {
            "Timestamp": int(time.time() * 1000),
            "CloudWatchMetrics": [{
                "Namespace": "O2/ChatSignal",
                "Dimensions": [["FunctionName", "Environment"]],
                "Metrics": [
                    {"Name": "BatchSize", "Unit": "Count"},
                    {"Name": "Success", "Unit": "Count"},
                    {"Name": "Retry", "Unit": "Count"},
                    {"Name": "SchemaRejected", "Unit": "Count"},
                    {"Name": "ProcessingDurationMs", "Unit": "Milliseconds"},
                    {"Name": "ColdStart", "Unit": "Count"},
                ],
            }],
        },
        "FunctionName": os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "o2-dev-chat-signal-worker"),
        "Environment": os.environ.get("DEPLOYMENT_ENVIRONMENT", "dev"),
        "BatchSize": batch_size,
        "Success": success,
        "Retry": retry,
        "SchemaRejected": rejected,
        "ProcessingDurationMs": duration_ms,
        "ColdStart": 1 if _COLD_START else 0,
    }
    print(json.dumps(payload, separators=(",", ":")))


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
    global _COLD_START
    started = time.perf_counter()
    records = event.get("Records", []) if isinstance(event, dict) else []
    if not isinstance(records, list):
        raise RuntimeError("CHAT_SIGNAL_SQS_RECORDS_INVALID")

    failures: list[dict[str, str]] = []
    success = 0
    rejected = 0
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
            success += 1
        except SchemaRejected as error:
            # Invalid input is acknowledged and deleted. Only the stable code is logged.
            LOGGER.warning(
                "chat_signal_schema_rejected message_id=%s error_code=%s",
                message_id,
                error.error_code,
            )
            rejected += 1
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

    _emit_metrics(
        batch_size=len(records),
        success=success,
        retry=len(failures),
        rejected=rejected,
        duration_ms=(time.perf_counter() - started) * 1000,
    )
    _COLD_START = False
    return {"batchItemFailures": failures}
