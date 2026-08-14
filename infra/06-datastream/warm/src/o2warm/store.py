"""DynamoDB 접근 계층.

## 키 설계

agent-data-requirements.md §7.2 를 그대로 따르되 두 가지를 더했습니다.

| pk | sk | 내용 | TTL |
|---|---|---|---|
| `METRIC#<service>` | `TS#<0패딩 epoch>` | 파생 지표 — **Agent가 읽는 것** | 7일 |
| `METRIC#<service>` | `SKETCH#<0패딩 epoch>` | 부분 집계 원본 — 병합용 | 1시간 |
| `METRIC#<service>` | `BASELINE#RPS` | 평시 기준 EWMA | 없음 |
| `CONTEXT#RUNDOWN` | `<broadcast_id>` | 방송 큐시트 | 없음 |
| `CONTEXT#DEPLOY#<service>` | `LATEST` | 배포 이력 | 30일 |
| `POLICY#<service>` / `TOPOLOGY#<service>` | `CURRENT` | 정책·의존성 | 없음 |
| `INCIDENT#<id>` | `SNAPSHOT#PRE` / `POST` | 조치 전후 | 30일 |

**sk 를 0으로 패딩합니다.** DynamoDB 정렬 키는 문자열 비교라
`TS#1786000100` 이 `TS#986000100` 보다 앞섭니다. 패딩하지 않으면
"최근 N개 윈도우"가 잘못 나옵니다.

SKETCH 를 METRIC 과 나눈 이유는, Agent가 읽는 아이템에 수십 KB짜리
스케치가 붙어 있으면 매 조회가 그만큼 비싸지기 때문입니다.
스케치가 원본이고 METRIC 은 그 투영입니다.

## 동시성

같은 윈도우에 두 스트림(비즈니스·클라이언트)이 각각 다른 Lambda 호출로
씁니다. 그래서 SKETCH 쓰기는 `rev` 기반 낙관적 잠금으로 처리하고,
실패하면 다시 읽어 병합합니다. METRIC 쓰기는 `rev` 가 더 큰 쪽만
살아남게 해 순서가 뒤집혀도 최신 상태로 수렴합니다.
"""

from __future__ import annotations

import base64
import gzip
import json
import time
from decimal import Decimal
from typing import Any

from .settings import settings
from .sketch import WindowSketch

SK_WIDTH = 12  # epoch 초를 0패딩할 자릿수


def metric_pk(service: str) -> str:
    return f"METRIC#{service}"


def ts_sk(window_start: int, prefix: str = "TS") -> str:
    return f"{prefix}#{int(window_start):0{SK_WIDTH}d}"


def _pack(sketch: WindowSketch) -> bytes:
    """스케치를 gzip JSON 으로 눌러 담습니다.

    맵을 그대로 DynamoDB 속성으로 펼치면 float→Decimal 변환이 필요하고
    아이템도 몇 배로 커집니다. 어차피 조회 조건이 되지 않는 데이터라
    한 덩어리 바이너리가 낫습니다.
    """
    raw = json.dumps(sketch.to_dict(), separators=(",", ":")).encode("utf-8")
    return gzip.compress(raw, 6)


def _unpack(blob: Any) -> WindowSketch:
    data = blob.value if hasattr(blob, "value") else blob
    if isinstance(data, str):  # base64 로 넘어온 경우 (低수준 클라이언트)
        data = base64.b64decode(data)
    return WindowSketch.from_dict(json.loads(gzip.decompress(data).decode("utf-8")))


def to_dynamo(value: Any) -> Any:
    """float 은 DynamoDB 가 받지 않으므로 Decimal 로 바꿉니다.

    None 은 그대로 둡니다(NULL 로 저장). '계산할 수 없었다'는 정보 자체가
    Agent 에게 필요하기 때문에, 없애면 안 됩니다.
    NaN·inf 는 Decimal 로도 저장할 수 없어 None 으로 떨어뜨립니다.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return None
        return Decimal(str(round(value, 6)))
    if isinstance(value, dict):
        return {k: to_dynamo(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_dynamo(v) for v in value]
    return value


def from_dynamo(value: Any) -> Any:
    if isinstance(value, Decimal):
        f = float(value)
        return int(f) if f.is_integer() else f
    if isinstance(value, dict):
        return {k: from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [from_dynamo(v) for v in value]
    return value


class ConcurrencyError(RuntimeError):
    """낙관적 잠금 재시도 소진. 배치를 실패시켜 Kinesis 재처리에 맡깁니다."""


class WarmStore:
    def __init__(self, table_name: str | None = None, region: str | None = None, table=None):
        if table is not None:
            self._table = table
            return
        import boto3  # 지연 임포트 — 계산 코어는 boto3 없이도 돌아야 합니다.

        self._table = boto3.resource(
            "dynamodb", region_name=region or settings.region
        ).Table(table_name or settings.table)

    # ------------------------------------------------------------ 스케치
    def load_sketch(self, service: str, window_start: int) -> tuple[WindowSketch | None, int]:
        resp = self._table.get_item(
            Key={"pk": metric_pk(service), "sk": ts_sk(window_start, "SKETCH")},
            ConsistentRead=True,
        )
        item = resp.get("Item")
        if not item or "blob" not in item:
            return None, 0
        return _unpack(item["blob"]), int(item.get("rev") or 0)

    def merge_sketch(self, partial: WindowSketch, attempts: int = 6) -> WindowSketch:
        """부분 집계를 윈도우에 병합하고 병합 결과를 돌려줍니다.

        읽기 → 병합 → 조건부 쓰기. 조건이 깨지면 다른 스트림이 먼저 쓴
        것이므로 다시 읽어 반복합니다. 샤드가 스트림당 하나인 현재 규모에서
        경쟁자는 최대 2명이라 재시도는 사실상 1회 안에 끝납니다.
        """
        from botocore.exceptions import ClientError

        for i in range(attempts):
            current, rev = self.load_sketch(partial.service, partial.window_start)
            merged = current if current is not None else WindowSketch(
                partial.service, partial.window_start
            )
            merged.merge(partial)

            if merged.n == rev:
                return merged  # 이미 반영된 배치 — 쓸 것이 없습니다.

            expires = int(time.time()) + settings.sketch_ttl_minutes * 60
            try:
                self._table.put_item(
                    Item={
                        "pk": metric_pk(partial.service),
                        "sk": ts_sk(partial.window_start, "SKETCH"),
                        "blob": _pack(merged),
                        "rev": merged.n,
                        "expires_at": expires,
                    },
                    ConditionExpression="attribute_not_exists(pk) OR #r = :prev",
                    ExpressionAttributeNames={"#r": "rev"},
                    ExpressionAttributeValues={":prev": rev},
                )
                return merged
            except ClientError as e:
                if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                    raise
                time.sleep(0.02 * (2**i))

        raise ConcurrencyError(
            f"{partial.service}@{partial.window_start} 병합 재시도 {attempts}회 소진"
        )

    # ------------------------------------------------------------ 지표
    def put_metrics(self, metrics: dict) -> None:
        """Agent가 읽는 아이템. rev 가 더 큰 쓰기만 살아남습니다."""
        from botocore.exceptions import ClientError

        item = to_dynamo(dict(metrics))
        item["pk"] = metric_pk(metrics["service"])
        item["sk"] = ts_sk(metrics["window_start"])
        item["expires_at"] = int(time.time()) + settings.metric_ttl_days * 86400
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) OR #r <= :rev",
                ExpressionAttributeNames={"#r": "rev"},
                ExpressionAttributeValues={":rev": metrics["rev"]},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise
            # 더 최신 상태가 이미 있습니다. 덮어쓰지 않는 것이 맞습니다.

    def recent_metrics(self, service: str, limit: int = 6) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        resp = self._table.query(
            KeyConditionExpression=Key("pk").eq(metric_pk(service))
            & Key("sk").begins_with("TS#"),
            ScanIndexForward=False,
            Limit=min(limit, settings.max_windows),
        )
        return [from_dynamo(i) for i in resp.get("Items", [])]

    def metrics_between(self, service: str, start: int, end: int) -> list[dict]:
        from boto3.dynamodb.conditions import Key

        resp = self._table.query(
            KeyConditionExpression=Key("pk").eq(metric_pk(service))
            & Key("sk").between(ts_sk(start), ts_sk(end)),
            ScanIndexForward=True,
            Limit=settings.max_windows,
        )
        return [from_dynamo(i) for i in resp.get("Items", [])]

    # ------------------------------------------------------------ 평시 기준
    def load_baseline(self, service: str) -> dict | None:
        resp = self._table.get_item(
            Key={"pk": metric_pk(service), "sk": "BASELINE#RPS"}, ConsistentRead=True
        )
        item = resp.get("Item")
        return from_dynamo(item) if item else None

    def save_baseline(self, service: str, baseline: dict) -> None:
        from botocore.exceptions import ClientError

        item = to_dynamo(dict(baseline))
        item["pk"] = metric_pk(service)
        item["sk"] = "BASELINE#RPS"
        try:
            self._table.put_item(
                Item=item,
                ConditionExpression="attribute_not_exists(pk) OR last_window < :w",
                ExpressionAttributeValues={":w": baseline["last_window"]},
            )
        except ClientError as e:
            if e.response["Error"]["Code"] != "ConditionalCheckFailedException":
                raise

    # ------------------------------------------------------------ 참조 데이터
    def get_item(self, pk: str, sk: str) -> dict | None:
        resp = self._table.get_item(Key={"pk": pk, "sk": sk})
        item = resp.get("Item")
        return from_dynamo(item) if item else None

    def deploy_context(self, service: str) -> dict | None:
        return self.get_item(f"CONTEXT#DEPLOY#{service}", "LATEST")

    def rundown(self, broadcast_id: str) -> dict | None:
        return self.get_item("CONTEXT#RUNDOWN", broadcast_id)

    def policy(self, service: str) -> dict | None:
        return self.get_item(f"POLICY#{service}", "CURRENT")

    def topology(self, service: str) -> dict | None:
        return self.get_item(f"TOPOLOGY#{service}", "CURRENT")

    # ------------------------------------------------------------ 인시던트
    def put_snapshot(self, incident_id: str, phase: str, data: dict) -> dict:
        """조치 전/후 스냅샷.

        §5 의 요구입니다. 조치 직전 값이 남아 있지 않으면 "무엇과 비교해
        복구인가"에 답할 수 없습니다.
        """
        phase = phase.upper()
        if phase not in ("PRE", "POST"):
            raise ValueError("phase 는 PRE 또는 POST 여야 합니다")
        item = to_dynamo({"recorded_at": time.time(), **data})
        item["pk"] = f"INCIDENT#{incident_id}"
        item["sk"] = f"SNAPSHOT#{phase}"
        item["expires_at"] = int(time.time()) + 30 * 86400
        self._table.put_item(Item=item)
        return {"incident_id": incident_id, "phase": phase}

    def get_snapshot(self, incident_id: str, phase: str) -> dict | None:
        return self.get_item(f"INCIDENT#{incident_id}", f"SNAPSHOT#{phase.upper()}")
