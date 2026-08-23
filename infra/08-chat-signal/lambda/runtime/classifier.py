"""Deterministic Korean latency-signal classifier.

Raw chat is accepted only as an in-memory argument. Classification results contain
stable rule identifiers and enums, never the source text or a digest of it.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


@dataclass(frozen=True)
class Classification:
    strength: str
    surface: str
    rule_ids: tuple[str, ...]

    @property
    def matched(self) -> bool:
        return self.strength in {"STRONG", "WEAK"}


UNRELATED = Classification("UNRELATED", "UNKNOWN", ())


def _normalize(message: str) -> str:
    normalized = unicodedata.normalize("NFKC", message).lower()
    return re.sub(r"\s+", " ", normalized).strip()


_EXCLUSION_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "recovery_or_negation",
        re.compile(
            r"(?:이제|지금은|현재는).*(?:정상|괜찮|빨라|잘\s*(?:돼|됨|나와|떠))"
            r"|(?:안|전혀)\s*느(?:리|려|린|림|렸)"
            r"|느리(?:지|지는)\s*않|정상(?:이에요|입니다|임|이네)?$"
        ),
    ),
    (
        "delivery_slowness",
        re.compile(r"(?:배송|택배|도착).*(?:느(?:리|려|린|림|렸)|늦|안\s*(?:와|옴))"),
    ),
    (
        "presenter_or_pacing_slowness",
        re.compile(
            r"(?:진행자|쇼호스트|말|말투|설명|방송\s*진행|전개)"
            r".*(?:느(?:리|려|린|림|렸)|늦)"
        ),
    ),
)

_LATENCY_OR_FAILURE = re.compile(
    r"느(?:리|려|린|림|렸)|늦게|오래\s*걸|로딩|렉(?:\s*걸)?|버벅|먹통|멈|끊|버퍼링"
    r"|안\s*(?:떠|뜸|나와|나옴|열려|열림|돼|됨|보여|보임|가|감)"
    r"|반응(?:이|이\s*)?\s*없|실패"
)

_SURFACE_RULES: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    (
        "READ_PATH",
        "read_loading_slow",
        re.compile(
            r"상품(?:\s*정보|\s*상세)?|상세\s*페이지|페이지|화면|이미지|목록|조회"
            r"|새로고침|버튼|주문|결제|재고|로딩"
        ),
    ),
    (
        "PLAYBACK",
        "playback_stall",
        re.compile(r"영상|동영상|재생|버퍼링|스트리밍|라이브\s*화면"),
    ),
    (
        "CHAT",
        "chat_lag",
        re.compile(r"채팅|메시지|전송|수신|채팅\s*연결"),
    ),
)

_WEAK_LATENCY = re.compile(r"느(?:리|려|린|림|렸)|렉(?:\s*걸)?|버벅")


def classify(message: str) -> Classification:
    """Classify one message using fixed precedence and stable rule identifiers."""

    text = _normalize(message)
    if not text:
        return UNRELATED

    for _rule_id, pattern in _EXCLUSION_RULES:
        if pattern.search(text):
            return UNRELATED

    if _LATENCY_OR_FAILURE.search(text):
        for surface, rule_id, pattern in _SURFACE_RULES:
            if pattern.search(text):
                return Classification("STRONG", surface, (rule_id,))

    if _WEAK_LATENCY.search(text):
        return Classification("WEAK", "UNKNOWN", ("generic_slow",))

    return UNRELATED
