"""liveness와 readiness 응답."""

from typing import Literal

from pydantic import BaseModel


class HealthOut(BaseModel):
    status: Literal["ok"]


class ReadinessOut(BaseModel):
    status: Literal["ok", "degraded"]
    mysql: bool
    valkey: bool
