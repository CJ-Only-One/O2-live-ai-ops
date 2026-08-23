from datetime import datetime, timezone
import json
import logging
import pathlib
import sys
import unittest


RUNTIME = pathlib.Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from handler import handler  # noqa: E402
from processor import ChatSignalProcessor  # noqa: E402
from repository import InMemoryRepository  # noqa: E402


def valid_body(message: str) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "event_id": "01K00000000000000000000001",
            "event_ts": "2026-08-22T00:00:01.000Z",
            "broadcast_id": "bc_1042",
            "user_key": "u_0123456789abcdef",
            "message": message,
            "trace_id": None,
        },
        ensure_ascii=False,
    )


class FixedNowProcessor(ChatSignalProcessor):
    def process_body(self, body: str, *, now=None):
        return super().process_body(
            body, now=datetime(2026, 8, 22, 0, 0, 4, tzinfo=timezone.utc)
        )


class ExplodingProcessor:
    def __init__(self, raw_message: str) -> None:
        self.raw_message = raw_message

    def process_body(self, _body: str):
        raise RuntimeError(f"failed while processing {self.raw_message}")


class HandlerTest(unittest.TestCase):
    def test_valid_message_is_acknowledged_without_raw_log(self) -> None:
        raw_message = "나만 느림?"
        event = {"Records": [{"messageId": "m-1", "body": valid_body(raw_message)}]}
        processor = FixedNowProcessor(InMemoryRepository())

        with self.assertLogs(level=logging.INFO) as captured:
            result = handler(event, None, processor=processor)

        self.assertEqual(result, {"batchItemFailures": []})
        self.assertNotIn(raw_message, "\n".join(captured.output))

    def test_invalid_schema_is_deleted_with_sanitized_code(self) -> None:
        raw_message = "상품 정보가 느려요"
        event = {"Records": [{"messageId": "m-1", "body": raw_message}]}
        processor = FixedNowProcessor(InMemoryRepository())

        with self.assertLogs(level=logging.WARNING) as captured:
            result = handler(event, None, processor=processor)

        self.assertEqual(result, {"batchItemFailures": []})
        rendered = "\n".join(captured.output)
        self.assertIn("BODY_NOT_JSON", rendered)
        self.assertNotIn(raw_message, rendered)

    def test_ac_009_exception_returns_identifier_only_and_never_logs_raw(self) -> None:
        raw_message = "새로고침해도 계속 로딩돼요"
        event = {"Records": [{"messageId": "m-9", "body": valid_body(raw_message)}]}

        with self.assertLogs(level=logging.ERROR) as captured:
            result = handler(event, None, processor=ExplodingProcessor(raw_message))

        self.assertEqual(result, {"batchItemFailures": [{"itemIdentifier": "m-9"}]})
        rendered = "\n".join(captured.output)
        self.assertNotIn(raw_message, rendered)
        self.assertNotIn(valid_body(raw_message), rendered)

    def test_missing_message_id_fails_batch_without_body_log(self) -> None:
        raw_message = "느려요"
        event = {"Records": [{"body": valid_body(raw_message)}]}

        with self.assertLogs(level=logging.ERROR) as captured:
            with self.assertRaisesRegex(
                RuntimeError, "CHAT_SIGNAL_SQS_MESSAGE_ID_MISSING"
            ):
                handler(event, None, processor=FixedNowProcessor(InMemoryRepository()))

        self.assertNotIn(raw_message, "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
