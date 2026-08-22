#!/usr/bin/env python3
"""원인 라벨별 횟수와 런북 유무를 낸다. 런북을 무엇부터 쓸지 정하는 도구다.

    python3 scripts/label-report.py

읽는 법.

    라벨                             횟수  런북
    queue_backlog_worker_shortage      5   없음   ⚠ 쓸 때 됐다
    monitor_false_alarm               11   있음
    other                              4          ⚠ 새 라벨 후보

언제 런북을 쓰나.

    severity 가 Critical / High   → 1회 겪으면 바로
    그 외                         → 같은 라벨 3회

  3회인 이유는 2회가 우연일 수 있어서다. 겪어 보고 조정할 눈금이지 상수가 아니다.

★ 사람이 기억해서 돌리는 일로 두면 안 돌아간다. 회고 때 또는 주 1회 돌린다.
★ `other` 가 쌓이면 그건 labels.txt 에 없는 원인이 반복된다는 뜻이다 —
  새 라벨을 만들 시점이다.
"""

import collections

import _history as H

REPEAT_THRESHOLD = 3


def main():
    _, s3vectors = H.clients()
    known = H.labels()
    have_runbook = H.runbook_labels()

    counts = collections.Counter()
    unverified = 0
    total = 0

    for hit in H.all_vectors(s3vectors):
        total += 1
        meta = hit.get("metadata") or {}
        if not meta.get("verified"):
            unverified += 1
            continue
        counts[meta.get("root_cause_label") or "unknown"] += 1

    print(f"인시던트 {total}건 · 검증됨 {total - unverified} · 미검증 {unverified}\n")

    if unverified:
        print(f"  ⚠ 미검증 {unverified}건은 집계에서 빠졌다. scripts/verify.py 로 채운다.\n")

    print(f"{'라벨':<34}{'횟수':>5}  {'런북':<6}")
    print("-" * 56)

    for label in sorted(known, key=lambda x: (-counts[x], x)):
        n = counts[label]
        if n == 0 and label not in have_runbook:
            continue
        book = "있음" if label in have_runbook else "없음"

        flag = ""
        if label == "other" and n:
            flag = "  ⚠ 새 라벨 후보"
        elif label not in have_runbook and n >= REPEAT_THRESHOLD:
            flag = "  ⚠ 쓸 때 됐다"
        print(f"{label:<34}{n:>5}  {book:<6}{flag}")

    stray = set(counts) - set(known)
    if stray:
        print("\n⚠ labels.txt 에 없는 라벨이 들어가 있다 —", ", ".join(sorted(stray)))
        print("  손으로 넣었거나 목록에서 지운 것이다. 목록을 고치거나 그 건을 다시 검증한다.")

    orphan = have_runbook - set(known)
    if orphan:
        print("\n⚠ 런북은 있는데 labels.txt 에 없는 라벨 —", ", ".join(sorted(orphan)))
        print("  파일명이 곧 라벨이므로 이 런북은 영원히 안 걸린다.")


if __name__ == "__main__":
    main()
