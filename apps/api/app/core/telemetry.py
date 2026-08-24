"""저카디널리티 DogStatsD 원자 계측.

Datadog 전송 실패는 요청 결과를 바꾸지 않는다. 비율과 백분위는 여기서 만들지 않고
Datadog query/formula가 counter와 distribution으로 계산한다.
"""

from __future__ import annotations

import os
import re
import socket
import math
from collections.abc import Mapping

_METRIC_TYPES = {
    "o2.app.business_event": "c",
    "o2.app.failure": "c",
    "o2.app.cache_access": "c",
    "o2.app.retry": "c",
    "o2.app.retry_eligible": "c",
    "o2.app.fallback": "c",
    "o2.app.fallback_attempt": "c",
    "o2.app.cancel": "c",
    "o2.app.order_create": "c",
    "o2.app.operation.duration": "d",
    "o2.app.db.pool.active": "g",
    "o2.app.db.pool.idle": "g",
    "o2.app.db.pool.overflow": "g",
}
_TAG_KEYS = {
    "env", "service", "version", "event", "result", "failure_code",
    "pod_name", "resource_name", "operation", "reason",
}
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")


def packet(metric: str, value: int | float, tags: Mapping[str, str]) -> bytes | None:
    metric_type = _METRIC_TYPES.get(metric)
    if metric_type is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    if any(key not in _TAG_KEYS or not _SAFE_VALUE.fullmatch(tag_value) for key, tag_value in tags.items()):
        return None
    suffix = ",".join(f"{key}:{tag_value}" for key, tag_value in tags.items())
    text = f"{metric}:{value}|{metric_type}" + (f"|#{suffix}" if suffix else "")
    return text.encode("ascii")


class Telemetry:
    def __init__(self) -> None:
        self.host = os.getenv("DD_AGENT_HOST", "")
        try:
            self.port = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))
        except ValueError:
            self.port = 0
        self.common_tags = {
            "env": os.getenv("DD_ENV", "dev"),
            "service": os.getenv("DD_SERVICE", "api"),
            "version": os.getenv("DD_VERSION", "unknown"),
            "pod_name": os.getenv("O2_POD_NAME", os.getenv("HOSTNAME", "unknown")),
        }
        self._socket: socket.socket | None = None

    def emit(self, metric: str, value: int | float = 1, **tags: str) -> None:
        payload = packet(metric, value, {**self.common_tags, **tags})
        if payload is None or not self.host or not 0 < self.port <= 65535:
            return
        try:
            self._socket = self._socket or socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.sendto(payload, (self.host, self.port))
        except OSError:
            try:
                if self._socket:
                    self._socket.close()
            finally:
                self._socket = None

    def business_event(self, event: str, result: str) -> None:
        self.emit("o2.app.business_event", event=event, result=result)

    def failure(self, event: str, failure_code: str) -> None:
        self.emit("o2.app.failure", event=event, failure_code=failure_code)

    def cache_access(self, hit: bool) -> None:
        self.emit("o2.app.cache_access", result="hit" if hit else "miss")

    def operation_duration(self, operation: str, duration_ms: int | float) -> None:
        self.emit("o2.app.operation.duration", duration_ms, operation=operation)

    def retry(self, operation: str, reason: str) -> None:
        self.emit("o2.app.retry_eligible", operation=operation)
        self.emit("o2.app.retry", operation=operation, reason=reason)

    def fallback(self, operation: str, used: bool) -> None:
        self.emit("o2.app.fallback_attempt", operation=operation)
        if used:
            self.emit("o2.app.fallback", operation=operation)

    def db_pool(self, role: str, *, active: int, idle: int, overflow: int) -> None:
        tags = {"operation": role}
        self.emit("o2.app.db.pool.active", max(0, active), **tags)
        self.emit("o2.app.db.pool.idle", max(0, idle), **tags)
        self.emit("o2.app.db.pool.overflow", max(0, overflow), **tags)


telemetry = Telemetry()
