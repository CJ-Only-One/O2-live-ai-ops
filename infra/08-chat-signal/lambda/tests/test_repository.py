import pathlib
import sys
import unittest


RUNTIME = pathlib.Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from repository import DynamoRepository  # noqa: E402


class IdentityCodec:
    def serialize(self, value):
        return value

    def deserialize(self, value):
        return value


class RecordingClient:
    def __init__(self) -> None:
        self.put_calls = []
        self.update_calls = []
        self.transact_calls = []
        self.items = {}

    def put_item(self, **kwargs):
        self.put_calls.append(kwargs)
        return {}

    def update_item(self, **kwargs):
        self.update_calls.append(kwargs)
        return {}

    def transact_write_items(self, **kwargs):
        self.transact_calls.append(kwargs)
        return {}

    def get_item(self, **kwargs):
        key = (kwargs["Key"]["pk"], kwargs["Key"]["sk"])
        item = self.items.get(key)
        return {"Item": item} if item else {}


def repository(client: RecordingClient) -> DynamoRepository:
    codec = IdentityCodec()
    return DynamoRepository(
        "incident-state",
        client=client,
        serializer=codec,
        deserializer=codec,
    )


class DynamoRepositoryTest(unittest.TestCase):
    def test_event_lifecycle_is_pending_then_completed_without_content(self) -> None:
        client = RecordingClient()
        repo = repository(client)

        self.assertTrue(repo.claim_event("01K00000000000000000000001", 1000))
        repo.complete_event("01K00000000000000000000001")

        event_item = client.put_calls[0]["Item"]
        self.assertEqual(event_item["status"], "PENDING")
        self.assertEqual(client.update_calls[0]["UpdateExpression"], "SET #status = :completed")
        self.assertNotIn("message", event_item)
        self.assertNotIn("hash", event_item)

    def test_user_vote_and_aggregate_are_one_transaction(self) -> None:
        client = RecordingClient()
        repo = repository(client)

        added = repo.add_vote(
            window_key="WINDOW#bc_1042#USER_PERCEIVED_LATENCY#2026-08-22T00:00:00.000Z",
            user_key="u_0123456789abcdef",
            strength="STRONG",
            surface="READ_PATH",
            rule_ids=("read_loading_slow",),
            window_start="2026-08-22T00:00:00.000Z",
            window_end="2026-08-22T00:00:15.000Z",
            expires_at=1000,
        )

        self.assertTrue(added)
        transaction = client.transact_calls[0]["TransactItems"]
        self.assertEqual(len(transaction), 2)
        self.assertEqual(
            transaction[0]["Put"]["ConditionExpression"], "attribute_not_exists(pk)"
        )
        self.assertIn("ADD matched_messages", transaction[1]["Update"]["UpdateExpression"])
        self.assertNotIn("message", transaction[0]["Put"]["Item"])
        self.assertNotIn("hash", transaction[0]["Put"]["Item"])
        self.assertNotIn("message", transaction[1]["Update"]["ExpressionAttributeValues"])
        self.assertNotIn("hash", transaction[1]["Update"]["ExpressionAttributeValues"])

    def test_candidate_and_cooldown_guard_are_created_atomically(self) -> None:
        client = RecordingClient()
        repo = repository(client)
        snapshot = {
            "window_start": "2026-08-22T00:00:00.000Z",
            "window_end": "2026-08-22T00:00:15.000Z",
            "matched_messages": 4,
            "unique_users": 4,
            "strong_signal_count": 3,
            "weak_signal_count": 1,
            "matched_rule_ids": ["generic_slow", "read_loading_slow"],
            "surface_counts": {"READ_PATH": 3, "PLAYBACK": 0, "CHAT": 0},
        }

        candidate, created = repo.record_candidate(
            proposed_candidate_id="cand_01K00000000000000000000001",
            broadcast_id="bc_1042",
            candidate_type="USER_PERCEIVED_LATENCY",
            snapshot=snapshot,
            created_at="2026-08-22T00:00:04.000Z",
            now_epoch=100,
            cooldown_seconds=60,
        )

        self.assertTrue(created)
        self.assertEqual(candidate["root_cause"], "UNDETERMINED")
        transaction = client.transact_calls[0]["TransactItems"]
        self.assertEqual(len(transaction), 2)
        self.assertTrue(transaction[0]["Put"]["Item"]["pk"].startswith("CANDIDATE#"))
        self.assertTrue(transaction[1]["Put"]["Item"]["pk"].startswith("ACTIVE#"))
        self.assertIn("cooldown_until <= :now", transaction[1]["Put"]["ConditionExpression"])


if __name__ == "__main__":
    unittest.main()
