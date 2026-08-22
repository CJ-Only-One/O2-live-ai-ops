import logging
import unittest

from handler import handler


class SkeletonHandlerTest(unittest.TestCase):
    def test_returns_every_message_as_failed_without_reading_body(self) -> None:
        raw_messages = ["상품 정보가 느려요", "나만 느림?"]
        event = {
            "Records": [
                {"messageId": "m-1", "body": raw_messages[0]},
                {"messageId": "m-2", "body": raw_messages[1]},
            ]
        }

        with self.assertLogs(level=logging.WARNING) as captured:
            result = handler(event, None)

        self.assertEqual(
            result,
            {
                "batchItemFailures": [
                    {"itemIdentifier": "m-1"},
                    {"itemIdentifier": "m-2"},
                ]
            },
        )
        rendered_logs = "\n".join(captured.output)
        for raw_message in raw_messages:
            self.assertNotIn(raw_message, rendered_logs)

    def test_missing_message_id_fails_the_whole_batch_without_body_log(self) -> None:
        raw_message = "새로고침해도 계속 로딩돼요"
        event = {"Records": [{"body": raw_message}]}

        with self.assertLogs(level=logging.ERROR) as captured:
            with self.assertRaisesRegex(
                RuntimeError,
                "CHAT_SIGNAL_SQS_MESSAGE_ID_MISSING",
            ):
                handler(event, None)

        self.assertNotIn(raw_message, "\n".join(captured.output))


if __name__ == "__main__":
    unittest.main()
