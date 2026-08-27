"""History 운영 도구의 인자 경계만 빠르게 점검한다."""

import seed_history
import verify


def _fails(fn, args):
    try:
        fn(args)
    except SystemExit:
        return
    raise AssertionError(f"실패해야 하는 인자: {args}")


def test_seed_selection():
    specs, verified = seed_history._select_specs([])
    assert [s["rca_type"] for s in specs] == ["chat_channel_overload"]
    assert verified is True

    specs, verified = seed_history._select_specs(["pg_external_failure", "--unverified"])
    assert [s["rca_type"] for s in specs] == ["pg_external_failure"]
    assert verified is False

    _fails(seed_history._select_specs, ["pg_external_failure", "typo"])
    _fails(seed_history._select_specs, ["--typo"])


def test_verify_terms():
    assert verify._search_terms(["결제", "PG", "--list"]) == ["결제", "pg"]
    _fails(verify._search_terms, ["--typo"])


if __name__ == "__main__":
    test_seed_selection()
    test_verify_terms()
    print("all passed")
