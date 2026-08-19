#!/usr/bin/env bash
# docs/decisions.md 의 상단 인덱스가 본문과 일치하는지 검사한다.
#
# 왜 필요한가:
#   결정 기록은 append-only 라 계속 자란다(현재 ~16,000토큰). 통째로 읽지 않고
#   인덱스에서 골라 그 절만 읽는 것이 전제인데, 결정을 추가하면서 인덱스를
#   빠뜨리면 그 전제가 무너진다. 다음 사람은 필요한 결정을 못 찾거나,
#   인덱스를 못 믿어서 전체를 다시 읽는다.
#
#   문서에 "인덱스도 같이 고치세요" 라고 적어두는 것으로는 지켜지지 않는다.
#
# 키워드 열은 검사하지 않는다. 사람이 판단할 영역이고,
# 여기서 검사하려 들면 스크립트가 문서를 소유하게 된다.

set -euo pipefail

DOC="${1:-docs/decisions.md}"
fail=0

# 본문 제목: "## D-015. ..." 에서 D-015 만 뽑는다.
headings=$(grep -oE '^## (D-[0-9]{3})\.' "$DOC" | grep -oE 'D-[0-9]{3}' | sort -u)

# 인덱스 행: "| D-015 | ... |" 에서 D-015 만 뽑는다.
indexed=$(grep -oE '^\| (D-[0-9]{3}) \|' "$DOC" | grep -oE 'D-[0-9]{3}' | sort -u)

# 같은 번호를 두 절이 쓰면 부분 읽기가 엉뚱한 절로 간다. sort -u 로 비교하면
# 중복이 지워져 보이지 않으므로 따로 센다 — 실제로 병합 사고가 이렇게 통과했다.
dup_head=$(grep -oE '^## (D-[0-9]{3})\.' "$DOC" | grep -oE 'D-[0-9]{3}' | sort | uniq -d)
dup_index=$(grep -oE '^\| (D-[0-9]{3}) \|' "$DOC" | grep -oE 'D-[0-9]{3}' | sort | uniq -d)

if [ -n "$dup_head" ]; then
  echo "✗ 같은 번호를 쓰는 절이 둘 이상이다:"
  echo "$dup_head" | sed 's/^/    /'
  fail=1
fi

if [ -n "$dup_index" ]; then
  echo "✗ 인덱스에 같은 번호가 두 번 있다:"
  echo "$dup_index" | sed 's/^/    /'
  fail=1
fi

# 병합 충돌 표식. 남은 채로 커밋된 적이 있다.
if grep -qE '^(<<<<<<<|=======$|>>>>>>>)' "$DOC"; then
  echo "✗ 병합 충돌 표식이 남아 있다:"
  grep -nE '^(<<<<<<<|=======$|>>>>>>>)' "$DOC" | sed 's/^/    /'
  fail=1
fi

missing=$(comm -23 <(echo "$headings") <(echo "$indexed"))
orphan=$(comm -13 <(echo "$headings") <(echo "$indexed"))

if [ -n "$missing" ]; then
  echo "✗ 본문에는 있는데 인덱스에 없다:"
  echo "$missing" | sed 's/^/    /'
  echo "  → $DOC 상단 '## 인덱스' 표에 한 줄 추가할 것"
  fail=1
fi

if [ -n "$orphan" ]; then
  echo "✗ 인덱스에는 있는데 본문에 없다:"
  echo "$orphan" | sed 's/^/    /'
  echo "  → 제목이 바뀌었거나 절이 사라졌다"
  fail=1
fi

# AGENTS.md 가 원본이고 CLAUDE.md 는 그것을 가져오기만 해야 한다.
# CLAUDE.md 에 내용이 다시 쓰이기 시작하면 두 파일이 갈린다.
if [ -f CLAUDE.md ] && ! grep -q '@AGENTS.md' CLAUDE.md; then
  echo "✗ CLAUDE.md 가 AGENTS.md 를 참조하지 않는다."
  echo "  → 내용은 AGENTS.md 한 곳에만 둔다"
  fail=1
fi

if [ "$fail" -eq 0 ]; then
  echo "✓ 인덱스 $(echo "$indexed" | wc -l | tr -d ' ')건 일치"
fi

exit "$fail"
