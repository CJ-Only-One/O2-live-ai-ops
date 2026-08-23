from datetime import datetime, timedelta, timezone
import json
import pathlib
import sys
import unittest


RUNTIME = pathlib.Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from processor import ChatSignalProcessor  # noqa: E402
from repository import InMemoryRepository, RepositoryError  # noqa: E402


BASE = datetime(2026, 8, 22, 0, 0, 0, tzinfo=timezone.utc)


def event_id(index: int) -> str:
    return f"01K0000000{index:016X}"


def signal(
    index: int,
    user: int,
    message: str,
    *,
    event_ts: datetime | None = None,
    broadcast_id: str = "bc_1042",
) -> str:
    return json.dumps(
        {
            "schema_version": "1.0",
            "event_id": event_id(index),
            "event_ts": (event_ts or (BASE + timedelta(seconds=1))).isoformat().replace(
                "+00:00", "Z"
            ),
            "broadcast_id": broadcast_id,
            "user_key": f"u_{user:016x}",
            "message": message,
            "trace_id": None,
        },
        ensure_ascii=False,
    )


class AcceptanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = InMemoryRepository()
        self.processor = ChatSignalProcessor(
            self.repository,
            candidate_id=lambda _now: f"cand_{event_id(999)}",
        )

    def process(
        self,
        index: int,
        user: int,
        message: str,
        *,
        event_ts: datetime | None = None,
        now: datetime | None = None,
    ) -> dict:
        return self.processor.process_body(
            signal(index, user, message, event_ts=event_ts),
            now=now or BASE + timedelta(seconds=4),
        )

    def test_ac_001_unrelated_chat_creates_no_candidate(self) -> None:
        for index, message in enumerate(
            ("오늘 할인 좋네요", "상품 예뻐요", "안녕하세요", "구매했어요"), 1
        ):
            self.assertEqual(self.process(index, index, message)["status"], "UNRELATED")
        self.assertEqual(self.repository.candidates, {})

    def test_ac_002_one_user_repeats_but_contributes_once(self) -> None:
        statuses = [
            self.process(index, 1, message)["status"]
            for index, message in enumerate(
                ("느려요", "느리네", "나만 느림?", "렉 걸린 것 같은데"), 1
            )
        ]
        self.assertEqual(statuses[0], "BELOW_THRESHOLD")
        self.assertEqual(statuses[1:], ["DUPLICATE_USER_VOTE"] * 3)
        window = next(iter(self.repository.windows.values()))
        self.assertEqual(window["matched_messages"], 1)
        self.assertEqual(window["unique_users"], 1)
        self.assertEqual(self.repository.candidates, {})

    def test_ac_003_three_strong_and_one_weak_create_read_candidate(self) -> None:
        messages = (
            "상품 정보가 늦게 떠요",
            "새로고침해도 계속 로딩돼요",
            "상품 이미지가 너무 느려요",
            "느리네",
        )
        results = [self.process(index, index, message) for index, message in enumerate(messages, 1)]
        self.assertEqual(results[-1]["status"], "CANDIDATE_CREATED")
        candidate = next(iter(self.repository.candidates.values()))
        self.assertEqual(candidate["suspected_surface"], "READ_PATH")
        self.assertEqual(candidate["confidence"], "MEDIUM")
        self.assertEqual(candidate["strong_signal_count"], 3)
        self.assertEqual(candidate["weak_signal_count"], 1)

    def test_ac_004_four_weak_users_create_low_unknown_candidate(self) -> None:
        for index, message in enumerate(
            ("느려요", "느리네", "나만 느림?", "렉 걸린 것 같은데"), 1
        ):
            result = self.process(index, index, message)
        self.assertEqual(result["status"], "CANDIDATE_CREATED")
        candidate = next(iter(self.repository.candidates.values()))
        self.assertEqual(candidate["suspected_surface"], "UNKNOWN")
        self.assertEqual(candidate["confidence"], "LOW")

    def test_ac_005_non_service_slowness_is_excluded(self) -> None:
        messages = (
            "배송이 너무 느려요",
            "진행자 말이 느리네요",
            "방송 진행이 느려요",
            "이제 정상이에요",
        )
        for index, message in enumerate(messages, 1):
            self.assertEqual(self.process(index, index, message)["status"], "UNRELATED")
        self.assertEqual(self.repository.candidates, {})

    def test_ac_006_duplicate_sqs_delivery_counts_once(self) -> None:
        body = signal(1, 1, "느려요")
        first = self.processor.process_body(body, now=BASE + timedelta(seconds=4))
        second = self.processor.process_body(body, now=BASE + timedelta(seconds=4))
        self.assertEqual(first["status"], "BELOW_THRESHOLD")
        self.assertEqual(second["status"], "DUPLICATE_EVENT")
        window = next(iter(self.repository.windows.values()))
        self.assertEqual(window["matched_messages"], 1)

    def test_ac_007_cooldown_updates_existing_candidate_across_windows(self) -> None:
        for index in range(1, 5):
            first = self.process(index, index, "느려요")
        first_candidate_id = first["candidate_id"]

        second_window = BASE + timedelta(seconds=16)
        for index in range(5, 9):
            second = self.process(
                index,
                index,
                "느리네",
                event_ts=second_window,
                now=BASE + timedelta(seconds=19),
            )
        self.assertEqual(second["status"], "CANDIDATE_UPDATED")
        self.assertEqual(second["candidate_id"], first_candidate_id)
        self.assertEqual(len(self.repository.candidates), 1)
        candidate = self.repository.candidates[first_candidate_id]
        self.assertEqual(candidate["matched_messages"], 8)
        self.assertEqual(candidate["unique_users"], 8)

    def test_ac_010_candidate_contract_has_no_raw_chat_or_hash(self) -> None:
        raw_messages = (
            "상품 정보가 늦게 떠요",
            "새로고침해도 계속 로딩돼요",
            "상품 이미지가 너무 느려요",
            "느리네",
        )
        for index, message in enumerate(raw_messages, 1):
            self.process(index, index, message)
        candidate = next(iter(self.repository.candidates.values()))
        self.assertEqual(candidate["metric_status"], "NOT_CHECKED")
        self.assertEqual(candidate["root_cause"], "UNDETERMINED")
        self.assertEqual(candidate["agent_handoff_status"], "NOT_CONFIGURED")
        self.assertFalse(candidate["raw_chat_included"])
        rendered = json.dumps(candidate, ensure_ascii=False)
        self.assertNotIn("hash", rendered.lower())
        for message in raw_messages:
            self.assertNotIn(message, rendered)

    def test_late_arrival_boundary_uses_event_time_window(self) -> None:
        event_ts = BASE + timedelta(seconds=14)
        accepted = self.process(
            1,
            1,
            "느려요",
            event_ts=event_ts,
            now=BASE + timedelta(seconds=19, milliseconds=999),
        )
        dropped = self.process(
            2,
            2,
            "느려요",
            event_ts=event_ts,
            now=BASE + timedelta(seconds=20, milliseconds=1),
        )
        self.assertEqual(accepted["status"], "BELOW_THRESHOLD")
        self.assertEqual(dropped["status"], "LATE_EVENT_DROPPED")

    def test_pending_event_recovers_after_failure_between_vote_and_candidate(self) -> None:
        class FailOnceAfterVoteRepository(InMemoryRepository):
            def __init__(self) -> None:
                super().__init__()
                self.fail_once = True

            def get_window(self, window_key: str) -> dict:
                if self.fail_once and self.windows[window_key]["matched_messages"] == 4:
                    self.fail_once = False
                    raise RepositoryError("DDB_GET_FAILED")
                return super().get_window(window_key)

        repository = FailOnceAfterVoteRepository()
        processor = ChatSignalProcessor(
            repository, candidate_id=lambda _now: f"cand_{event_id(998)}"
        )
        for index in range(1, 4):
            processor.process_body(
                signal(index, index, "느려요"), now=BASE + timedelta(seconds=4)
            )

        fourth = signal(4, 4, "느려요")
        with self.assertRaisesRegex(RepositoryError, "DDB_GET_FAILED"):
            processor.process_body(fourth, now=BASE + timedelta(seconds=4))

        recovered = processor.process_body(fourth, now=BASE + timedelta(seconds=4))
        self.assertEqual(recovered["status"], "CANDIDATE_CREATED")
        self.assertEqual(len(repository.candidates), 1)
        candidate = next(iter(repository.candidates.values()))
        self.assertEqual(candidate["matched_messages"], 4)


if __name__ == "__main__":
    unittest.main()
