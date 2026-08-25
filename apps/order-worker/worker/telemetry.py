"""order-worker용 fail-open DogStatsD 원자 계측."""

from __future__ import annotations

import os
import re
import socket
import math
from collections.abc import Mapping

_METRIC_TYPES = {
    "o2.app.business_event": "c",
    "o2.app.failure": "c",
    "o2.app.cancel": "c",
    "o2.app.retry": "c",
    "o2.app.retry_eligible": "c",
    "o2.app.batch.size": "d",
    "o2.app.operation.duration": "d",
}
_TAG_KEYS = {"env", "service", "version", "event", "result", "failure_code", "pod_name", "operation", "reason"}
_SAFE_VALUE = re.compile(r"^[A-Za-z0-9_.:/-]{1,80}$")


def packet(metric: str, value: int | float, tags: Mapping[str, str]) -> bytes | None:
    metric_type = _METRIC_TYPES.get(metric)
    if metric_type is None or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    if any(key not in _TAG_KEYS or not _SAFE_VALUE.fullmatch(tag_value) for key, tag_value in tags.items()):
        return None
    suffix = ",".join(f"{key}:{tag_value}" for key, tag_value in tags.items())
    return (f"{metric}:{value}|{metric_type}" + (f"|#{suffix}" if suffix else "")).encode("ascii")


class Telemetry:
    def __init__(self) -> None:
        self.host = os.getenv("DD_AGENT_HOST", "")
        try:
            self.port = int(os.getenv("DD_DOGSTATSD_PORT", "8125"))
        except ValueError:
            self.port = 0
        self.common_tags = {
            "env": os.getenv("DD_ENV", "dev"),
            "service": os.getenv("DD_SERVICE", "order-worker"),
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

    def order_confirm(self, result: str, duration_ms: int | float) -> None:
        self.emit("o2.app.business_event", event="order.confirm", result=result)
        self.emit("o2.app.operation.duration", duration_ms, operation="order.confirm")

    def failure(self, failure_code: str) -> None:
        self.emit("o2.app.failure", event="order.confirm", failure_code=failure_code)

    def cancel(self, reason: str) -> None:
        self.emit("o2.app.cancel", reason=reason)

    def retry(self, reason: str) -> None:
        self.emit("o2.app.retry_eligible", operation="order.confirm")
        self.emit("o2.app.retry", operation="order.confirm", reason=reason)

    def batch(self, size: int, duration_ms: int | float) -> None:
        self.emit("o2.app.batch.size", size, operation="order.confirm")
        self.emit("o2.app.operation.duration", duration_ms, operation="order.batch")


telemetry = Telemetry()
