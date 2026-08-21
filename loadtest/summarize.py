"""run.sh 가 남긴 계단별 원자료를 표 한 장으로 접는다.

계단 하나가 끝날 때마다 한 줄을 찍고, 전부 끝나면 표를 다시 낸다.
표는 그대로 docs/measurements.md 로 옮긴다.

단독으로도 쓴다 — 중간에 끊긴 실행의 결과 디렉터리를 넘기면 거기까지의 표가 나온다:

    python3 loadtest/summarize.py loadtest/results/20260821-120000 --table
"""

import json
import pathlib
import sys


def _num(text: str) -> float:
    """kubectl top 의 `123m` `142Mi` 를 숫자로. 단위는 호출자가 안다."""
    return float("".join(c for c in text if c.isdigit() or c == "."))


def peak(path: pathlib.Path, tracked: list[str]) -> dict[str, tuple[float, float, int]]:
    """디플로이먼트별 (CPU 합 최대, 메모리 합 최대, 파드 수).

    합으로 보는 이유는 레플리카가 늘면 파드 하나당 값이 줄기 때문이다.
    파드당 계수가 필요하면 합을 파드 수로 나눈다 — 그래서 개수도 같이 낸다.
    최댓값을 쓰는 것은 평균이 램프 구간에 희석되기 때문이다.
    """
    if not path.exists():
        return {}

    by_ts: dict[str, dict[str, list[tuple[float, float]]]] = {}
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 4:
            continue
        ts, pod, cpu, mem = parts[0], parts[1], parts[2], parts[3]
        # 파드 이름에서 replicaset 해시와 파드 접미사를 떼면 디플로이먼트다.
        deploy = "-".join(pod.split("-")[:-2]) or pod
        if deploy not in tracked:
            continue
        by_ts.setdefault(ts, {}).setdefault(deploy, []).append((_num(cpu), _num(mem)))

    out: dict[str, tuple[float, float, int]] = {}
    for per_deploy in by_ts.values():
        for deploy, vals in per_deploy.items():
            cpu = sum(v[0] for v in vals)
            mem = sum(v[1] for v in vals)
            prev = out.get(deploy, (0.0, 0.0, 0))
            out[deploy] = (max(prev[0], cpu), max(prev[1], mem), max(prev[2], len(vals)))
    return out


def k6_process(path: pathlib.Path) -> dict[str, float | None]:
    """부하 생성기 자신의 최대 사용량.

    이 값이 없으면 "서버가 느려졌다"와 "k6 가 못 따라갔다"를 구분할 수 없다.
    macOS 의 `ps %cpu` 는 프로세스 시작 이후 누적 평균이라 순간 피크는 아니다.
    코어 수만큼 100 을 넘을 수 있다 — 10코어면 상한이 1000 이다.
    """
    if not path.exists():
        return {"k6_cpu": None, "k6_rss": None}
    cpu = rss = 0.0
    for line in path.read_text().splitlines():
        parts = line.split()
        if len(parts) < 3:
            continue
        cpu = max(cpu, float(parts[1]))
        rss = max(rss, float(parts[2]) / 1024)  # KB -> MiB
    return {"k6_cpu": cpu or None, "k6_rss": rss or None}


def k6_row(path: pathlib.Path) -> dict[str, float | None]:
    """k6 요약에서 표에 들어갈 것만 꺼낸다.

    임계 통과 여부는 안 읽는다 — 요약이 판정을 어떤 불리언으로 적는지가
    버전마다 흔들려서, 원값을 직접 비교하는 편이 안 깨진다.
    """
    if not path.exists():
        return {}
    m = json.loads(path.read_text()).get("metrics", {})

    def get(name: str, field: str):
        return m.get(name, {}).get(field)

    failed = m.get("http_req_failed", {})
    total = (failed.get("passes") or 0) + (failed.get("fails") or 0)

    # 전달률. 샘플 소켓 하나는 발화 전부를 받아야 정상이므로 분모가
    # 발화 건수 × 샘플 소켓 수다. 이건 k6 임계로 못 쓴다 — 임계식이 지표
    # 하나만 보기 때문이다. 그래서 여기서 계산하고 종료 코드로 알린다.
    sent = get("chat_sent", "count")
    sampled = get("ws_sampled", "count")
    items = get("chat_items_received", "count")
    expected = (sent or 0) * (sampled or 0)

    return {
        "p95": get("http_req_duration", "p(95)"),
        "p99": get("http_req_duration", "p(99)"),
        "rps": get("http_reqs", "rate"),
        # http_req_failed 는 passes 가 "실패한 요청 수"다. 이름이 헷갈리므로
        # 비율은 직접 계산한다.
        "fail_pct": (failed["passes"] / total * 100) if total else None,
        "dropped": get("dropped_iterations", "count"),
        "ws_opened": get("ws_opened", "count"),
        "ws_failed": get("ws_failed", "count"),
        "ws_closed_early": get("ws_closed_early", "count"),
        "chat_sent": sent,
        "delivery_pct": (items / expected * 100) if expected else None,
        "chat_p95": get("chat_latency_ms", "p(95)"),
        "chat_p99": get("chat_latency_ms", "p(99)"),
        "bad": get("chat_bad_frames", "count"),
        "frames": get("chat_frames_received", "rate"),
    }


COLUMNS = [
    ("p95", "p95(ms)", "{:.0f}"),
    ("p99", "p99(ms)", "{:.0f}"),
    ("rps", "RPS", "{:.0f}"),
    ("fail_pct", "실패%", "{:.2f}"),
    ("dropped", "드롭", "{:.0f}"),
    ("ws_opened", "연결", "{:.0f}"),
    ("ws_failed", "연결실패", "{:.0f}"),
    ("ws_closed_early", "조기종료", "{:.0f}"),
    ("chat_sent", "발화", "{:.0f}"),
    ("delivery_pct", "전달%", "{:.1f}"),
    ("chat_p95", "전파p95", "{:.0f}"),
    ("chat_p99", "전파p99", "{:.0f}"),
    ("bad", "깨진프레임", "{:.0f}"),
    ("frames", "프레임/s", "{:.0f}"),
    # 마지막 두 열은 서버가 아니라 **부하 생성기** 다. 여기가 포화하면
    # 왼쪽 숫자가 전부 무효다.
    ("k6_cpu", "k6 CPU%", "{:.0f}"),
    ("k6_rss", "k6 MEM", "{:.0f}"),
]

# 전달률이 이 아래면 계단을 실패로 본다. 100 이 아니라 99 인 것은 소켓을
# 닫는 순간 날아가던 마지막 프레임이 한둘 빠지기 때문이다.
DELIVERY_MIN = 99.0


def render(rows: list[dict], tracked: list[str]) -> str:
    # 값이 하나도 없는 열은 뺀다. 읽기 경로와 채팅이 서로 다른 지표를 낸다.
    cols = [c for c in COLUMNS if any(r.get(c[0]) is not None for r in rows)]
    deploys = [d for d in tracked if any(d in r["peak"] for r in rows)]

    head = [rows[0]["var"]] + [c[1] for c in cols]
    for d in deploys:
        head += [f"{d} CPU", f"{d} MEM"]

    body = []
    for r in rows:
        line = [str(r["step"])]
        for key, _, fmt in cols:
            v = r.get(key)
            line.append(fmt.format(v) if v is not None else "-")
        for d in deploys:
            cpu, mem, n = r["peak"].get(d, (0.0, 0.0, 0))
            # 파드 수를 붙인다. 2 파드의 480m 과 1 파드의 480m 은 다른 얘기다.
            line += [f"{cpu:.0f}m×{n}" if n else "-", f"{mem:.0f}Mi" if n else "-"]
        body.append(line)

    width = [max(len(h), *(len(b[i]) for b in body)) for i, h in enumerate(head)]
    out = ["  ".join(h.rjust(width[i]) for i, h in enumerate(head))]
    out.append("  ".join("-" * w for w in width))
    out += ["  ".join(c.rjust(width[i]) for i, c in enumerate(b)) for b in body]
    return "\n".join(out)


def load(outdir: pathlib.Path, tracked: list[str]) -> list[dict]:
    rows = []
    # 파일 이름 사전순이면 step-10 이 step-5 보다 앞에 온다. 숫자로 정렬한다.
    metas = sorted(outdir.glob("step-*.meta"), key=lambda p: int(p.stem.split("-")[1]))
    for meta_path in metas:
        meta = json.loads(meta_path.read_text())
        stem = meta_path.with_suffix("")
        rows.append(
            {
                **meta,
                **k6_row(stem.with_suffix(".json")),
                **k6_process(stem.with_suffix(".k6")),
                "peak": peak(stem.with_suffix(".pods"), tracked),
            }
        )
    return rows


def main() -> None:
    outdir = pathlib.Path(sys.argv[1])

    if sys.argv[2] == "--table":
        tracked = sys.argv[3].split()
        rows = load(outdir, tracked)
        if rows:
            print(render(rows, tracked))
            print(f"\n원자료: {outdir}")
        return

    var, step, rc, tracked = sys.argv[2], sys.argv[3], int(sys.argv[4]), sys.argv[5].split()
    # 계단 순서를 파일 이름의 사전순이 아니라 숫자 크기로 유지한다.
    (outdir / f"step-{step}.meta").write_text(
        json.dumps({"var": var, "step": int(step), "rc": rc})
    )
    rows = load(outdir, tracked)
    rows.sort(key=lambda r: r["step"])
    row = rows[-1]
    print(render([row], tracked))

    # k6 임계는 지표 하나만 본다. 두 지표를 나눠야 나오는 전달률은 여기서
    # 판정해 종료 코드로 알린다 — run.sh 가 이걸 보고 멈춘다.
    delivered = row.get("delivery_pct")
    if delivered is not None and delivered < DELIVERY_MIN:
        print(f"  전달률 {delivered:.1f}% < {DELIVERY_MIN}% — 채팅이 유실됐다")
        sys.exit(1)


if __name__ == "__main__":
    main()
