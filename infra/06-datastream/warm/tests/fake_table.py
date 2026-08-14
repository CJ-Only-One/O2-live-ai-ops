"""boto3 Table 을 흉내 내는 최소 구현.

moto 를 붙이면 의존성이 늘고, 정작 검증하고 싶은 것은 DynamoDB 자체가
아니라 **우리 쪽 낙관적 잠금 로직**입니다. 조건부 쓰기와 정렬 키 질의만
정확히 흉내 내면 충분합니다.
"""

from __future__ import annotations

import re
from decimal import Decimal


from botocore.exceptions import ClientError


def _conditional_check_failed() -> ClientError:
    """실제 botocore 예외를 그대로 씁니다.

    자체 예외를 던지면 store.py 의 `except ClientError` 를 비껴가
    재시도 경로가 검증되지 않은 채 통과합니다.
    """
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException",
                   "Message": "The conditional request failed"}},
        "PutItem",
    )


class FakeTable:
    def __init__(self):
        self.items: dict[tuple[str, str], dict] = {}
        self.puts = 0
        self.conflicts = 0

    # ------------------------------------------------------------ 조회
    def get_item(self, Key, ConsistentRead=False, **kw):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": dict(item)} if item else {}

    def query(self, KeyConditionExpression=None, ScanIndexForward=True, Limit=100, **kw):
        pk, lo, hi, prefix = _parse_condition(KeyConditionExpression)
        rows = []
        for (p, s), item in self.items.items():
            if p != pk:
                continue
            if prefix is not None and not s.startswith(prefix):
                continue
            if lo is not None and not (lo <= s <= hi):
                continue
            rows.append(item)
        rows.sort(key=lambda i: i["sk"], reverse=not ScanIndexForward)
        return {"Items": [dict(r) for r in rows[:Limit]]}

    # ------------------------------------------------------------ 쓰기
    def put_item(self, Item, ConditionExpression=None,
                 ExpressionAttributeNames=None, ExpressionAttributeValues=None, **kw):
        key = (Item["pk"], Item["sk"])
        if ConditionExpression and not _evaluate(
            ConditionExpression, self.items.get(key),
            ExpressionAttributeNames or {}, ExpressionAttributeValues or {},
        ):
            self.conflicts += 1
            raise _conditional_check_failed()
        self.items[key] = dict(Item)
        self.puts += 1
        return {}


def _parse_condition(cond):
    """boto3 Key 조건식에서 pk 와 sk 범위를 뽑아냅니다."""
    expr = cond.get_expression()
    if expr["operator"] == "AND":
        left, right = expr["values"]
        pk = left.get_expression()["values"][1]
        r = right.get_expression()
        op, vals = r["operator"], r["values"][1:]
        if op == "begins_with":
            return pk, None, None, vals[0]
        if op == "BETWEEN":
            return pk, vals[0], vals[1], None
        return pk, vals[0], vals[0], None
    return expr["values"][1], None, None, None


def _evaluate(expression, item, names, values):
    """이 코드가 실제로 쓰는 세 가지 조건식만 해석합니다."""
    def sub(text):
        for alias, real in names.items():
            text = text.replace(alias, real)
        return text

    expression = sub(expression)

    for clause in [c.strip() for c in expression.split(" OR ")]:
        if clause.startswith("attribute_not_exists("):
            if item is None:
                return True
            continue
        m = re.match(r"^(\w+)\s*(<=|>=|<|>|=)\s*(:\w+)$", clause)
        if not m:
            raise AssertionError(f"흉내 낼 수 없는 조건식: {clause}")
        attr, op, ref = m.groups()
        expected = values[ref]
        actual = (item or {}).get(attr, 0)
        if isinstance(actual, Decimal):
            actual = int(actual)
        if isinstance(expected, Decimal):
            expected = int(expected)
        if {"=": actual == expected, "<=": actual <= expected, ">=": actual >= expected,
            "<": actual < expected, ">": actual > expected}[op]:
            return True
    return False
