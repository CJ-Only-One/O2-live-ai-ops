import pathlib
import sys
import unittest


RUNTIME = pathlib.Path(__file__).resolve().parents[1] / "runtime"
sys.path.insert(0, str(RUNTIME))

from classifier import classify  # noqa: E402


class ClassifierTest(unittest.TestCase):
    def test_strong_signals_require_surface_and_symptom(self) -> None:
        cases = {
            "상품 정보가 늦게 떠요": ("STRONG", "READ_PATH", "read_loading_slow"),
            "영상이 계속 멈춰요": ("STRONG", "PLAYBACK", "playback_stall"),
            "채팅 전송이 너무 느려요": ("STRONG", "CHAT", "chat_lag"),
        }
        for message, expected in cases.items():
            with self.subTest(message=message):
                result = classify(message)
                self.assertEqual(
                    (result.strength, result.surface, result.rule_ids[0]), expected
                )

    def test_generic_latency_is_weak(self) -> None:
        for message in ("나만 느림?", "느리네", "렉 걸린 것 같은데"):
            with self.subTest(message=message):
                result = classify(message)
                self.assertEqual(result.strength, "WEAK")
                self.assertEqual(result.surface, "UNKNOWN")
                self.assertEqual(result.rule_ids, ("generic_slow",))

    def test_exclusion_negation_and_recovery_run_first(self) -> None:
        messages = (
            "배송이 너무 느려요",
            "진행자 말이 느리네요",
            "방송 진행이 느려요",
            "이제 정상이에요",
            "지금은 안 느려요",
        )
        for message in messages:
            with self.subTest(message=message):
                result = classify(message)
                self.assertEqual(result.strength, "UNRELATED")
                self.assertFalse(result.matched)


if __name__ == "__main__":
    unittest.main()
