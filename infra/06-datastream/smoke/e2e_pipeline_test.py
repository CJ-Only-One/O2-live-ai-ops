"""O2 Warm/Cold 데이터 파이프라인 E2E 통합 테스트.

실행 전제:
  - AWS_PROFILE=o2-data (기본값), AWS_REGION=ap-northeast-2 (기본값)
  - boto3, pandas, pyarrow 설치
  - Terraform으로 Kinesis/Lambda/DynamoDB/Firehose/Glue 리소스 배포 완료
"""

from __future__ import annotations

import gzip
import io
import json
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import boto3
import pandas as pd
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError


AWS_PROFILE = os.getenv("AWS_PROFILE", "o2-data")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-2")
STREAM_NAME = "stream-business"
TABLE_NAME = "o2-agent-context"
BUCKET_NAME = "o2-data-lake-066107819912"
RAW_PREFIX = "raw/business/"
ML_READY_PREFIX = "ml-ready/"
GLUE_JOB_NAME = "o2-ml-data-prep-job"
EVENT_COUNT = 100

# Windows 기본 CP949 콘솔에서도 상태 아이콘과 한글을 안전하게 출력한다.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def json_default(value: Any) -> Any:
    """DynamoDB Decimal 등 콘솔 출력용 JSON 비표준 타입을 변환한다."""
    if isinstance(value, Decimal):
        return int(value) if value % 1 == 0 else float(value)
    raise TypeError(f"Cannot serialize {type(value).__name__}")


def make_events(now: datetime) -> list[dict[str, Any]]:
    """이벤트 스키마 계약 v0.2에 맞는 coupon/payment 이벤트 100건을 만든다."""
    rng = random.Random(20260813)
    run_id = uuid.uuid4().hex[:12]
    events: list[dict[str, Any]] = []

    for index in range(EVENT_COUNT):
        event_time = now + timedelta(milliseconds=index * 20)
        is_coupon = index % 2 == 0
        event_name = "coupon.issue" if is_coupon else "payment.process"
        service = "coupon-api" if is_coupon else "payment-api"
        failed = index % 10 == 9

        if is_coupon:
            payload = {
                "coupon_id": f"CP-E2E-{index:03d}",
                "campaign_id": "E2E-PIPELINE",
                "result": "FAILED" if failed else "SUCCESS",
                "latency_ms": rng.randint(40, 180),
                "is_retry": index % 20 == 0,
            }
            if failed:
                payload["failure_code"] = "SOLD_OUT"
        else:
            payload = {
                "order_id": f"ORDER-E2E-{index:03d}",
                "payment_id": f"PAY-E2E-{index:03d}",
                "amount": 25000 + index,
                "result": "FAILED" if failed else "SUCCESS",
                "retry_count": 1 if index % 20 == 1 else 0,
                "pg_latency_ms": rng.randint(20, 100),
                "total_latency_ms": rng.randint(100, 350),
            }
            if failed:
                payload["failure_code"] = "PG_TIMEOUT"

        timestamp = event_time.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        events.append(
            {
                "event_id": f"e2e-{run_id}-{index:03d}",
                "event_name": event_name,
                "schema_version": "0.2",
                "event_ts": timestamp,
                "received_ts": timestamp,
                "service": service,
                "service_version": "e2e-1.0.0",
                "trace_id": f"trace-{run_id}-{index:03d}",
                "broadcast_id": f"E2E-{run_id}",
                "user_key": f"user-{index % 25:03d}",
                "session_id": f"session-{index % 10:03d}",
                "client_ip_key": f"ip-{index % 20:03d}",
                "payload": payload,
            }
        )
    return events


def inject_events(kinesis: Any, events: list[dict[str, Any]]) -> None:
    records = [
        {
            "Data": (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"),
            "PartitionKey": event["user_key"],
        }
        for event in events
    ]
    response = kinesis.put_records(StreamName=STREAM_NAME, Records=records)
    failed = response.get("FailedRecordCount", 0)
    if failed:
        errors = [record for record in response["Records"] if "ErrorCode" in record]
        raise RuntimeError(f"Kinesis 주입 {failed}건 실패: {errors[:3]}")

    print("✅ 100건 데이터 Kinesis 주입 완료")
    print("샘플 데이터:")
    print(json.dumps(events[0], ensure_ascii=False, indent=2))


def show_warm_results(table: Any, services: set[str]) -> None:
    print("\n⏳ Lambda 집계를 위해 10초 대기합니다...")
    time.sleep(10)
    items: list[dict[str, Any]] = []
    for service in sorted(services):
        response = table.query(
            KeyConditionExpression=Key("pk").eq(f"METRIC#{service}")
            & Key("sk").begins_with("TS#"),
            ScanIndexForward=False,
            Limit=3,
            ConsistentRead=True,
        )
        items.extend(response.get("Items", []))

    items.sort(key=lambda item: item.get("sk", ""), reverse=True)
    if not items:
        raise RuntimeError("DynamoDB에서 최신 Warm 집계 결과를 찾지 못했습니다.")
    print("✅ DynamoDB 최신 Warm 산출물:")
    print(json.dumps(items[:3], ensure_ascii=False, indent=2, default=json_default))


def list_objects(s3: Any, prefix: str) -> list[dict[str, Any]]:
    objects: list[dict[str, Any]] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        objects.extend(page.get("Contents", []))
    return objects


def wait_for_raw_object(s3: Any, started_at: datetime) -> dict[str, Any]:
    print("\n⏳ Firehose 버퍼(최대 약 300초)를 기다리며 신규 Raw 객체를 확인합니다.")
    deadline = time.monotonic() + 420
    while time.monotonic() < deadline:
        candidates = [
            obj
            for obj in list_objects(s3, RAW_PREFIX)
            if obj["LastModified"] >= started_at - timedelta(seconds=5)
        ]
        if candidates:
            newest = max(candidates, key=lambda obj: obj["LastModified"])
            # 신규 파일 안에 이번 실행의 event_id가 있는지 확인해 이전 버퍼와 구분한다.
            body = s3.get_object(Bucket=BUCKET_NAME, Key=newest["Key"])["Body"].read()
            try:
                decoded = gzip.decompress(body).decode("utf-8")
            except gzip.BadGzipFile:
                decoded = body.decode("utf-8")
            if "e2e-" in decoded:
                print(f"✅ Firehose Raw 파일 확인: s3://{BUCKET_NAME}/{newest['Key']}")
                return newest
        print("  아직 신규 Raw 파일이 없습니다. 15초 후 다시 확인합니다...")
        time.sleep(15)
    raise TimeoutError("7분 안에 이번 테스트의 Firehose Raw 파일을 찾지 못했습니다.")


def run_glue_job(glue: Any) -> str:
    print(f"\n▶ Glue Job 즉시 실행: {GLUE_JOB_NAME}")
    start_deadline = time.monotonic() + 300
    while True:
        try:
            job_run_id = glue.start_job_run(JobName=GLUE_JOB_NAME)["JobRunId"]
            break
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code")
            if code != "ConcurrentRunsExceededException" or time.monotonic() >= start_deadline:
                raise
            print("  직전 Glue 실행 정리 중입니다. 15초 후 시작을 재시도합니다...")
            time.sleep(15)
    terminal_states = {"SUCCEEDED", "FAILED", "STOPPED", "TIMEOUT", "ERROR", "EXPIRED"}
    while True:
        run = glue.get_job_run(
            JobName=GLUE_JOB_NAME, RunId=job_run_id, PredecessorsIncluded=False
        )["JobRun"]
        state = run["JobRunState"]
        print(f"  Glue Job {job_run_id}: {state}")
        if state in terminal_states:
            if state != "SUCCEEDED":
                detail = run.get("ErrorMessage", "오류 상세 없음")
                raise RuntimeError(f"Glue Job {state}: {detail}")
            print("✅ Glue Job 성공")
            return job_run_id
        time.sleep(15)


def show_parquet_result(s3: Any, glue_started_at: datetime) -> None:
    parquet_objects = [
        obj
        for obj in list_objects(s3, ML_READY_PREFIX)
        if obj["Key"].endswith(".parquet") and obj["LastModified"] >= glue_started_at
    ]
    if not parquet_objects:
        raise RuntimeError("Glue 실행 후 생성된 ml-ready Parquet 파일을 찾지 못했습니다.")
    newest = max(parquet_objects, key=lambda obj: obj["LastModified"])
    parquet_data = s3.get_object(Bucket=BUCKET_NAME, Key=newest["Key"])["Body"].read()
    frame = pd.read_parquet(io.BytesIO(parquet_data), engine="pyarrow")

    expected = {"event_ts", "event_name", "trace_id", "payload"}
    missing = expected.difference(frame.columns)
    if missing:
        raise AssertionError(f"Parquet 필수 컬럼 누락: {sorted(missing)}")
    if not frame["payload"].dropna().map(lambda value: isinstance(value, str)).all():
        raise AssertionError("payload 컬럼에 문자열이 아닌 값이 있습니다.")

    print(f"\n✅ 최신 Parquet 확인: s3://{BUCKET_NAME}/{newest['Key']}")
    print("\nDataFrame head(5):")
    print(frame.head(5).to_string(index=False))
    print("\nDataFrame info():")
    frame.info(buf=sys.stdout)


def main() -> None:
    session = boto3.Session(profile_name=AWS_PROFILE, region_name=AWS_REGION)
    kinesis = session.client("kinesis")
    s3 = session.client("s3")
    glue = session.client("glue")
    table = session.resource("dynamodb").Table(TABLE_NAME)

    resuming = os.getenv("E2E_SKIP_INJECTION") == "1"
    resume_at_glue = os.getenv("E2E_RESUME_AT_GLUE") == "1"
    # 재개 실행은 직전 프로세스에서 주입한 객체까지 탐색할 수 있도록 범위를 넓힌다.
    started_at = datetime.now(timezone.utc) - (timedelta(minutes=15) if resuming else timedelta())
    events = make_events(started_at)
    if resume_at_glue:
        print("ℹ️ 검증 완료된 주입/Warm/Raw 단계를 건너뛰고 Glue부터 재개합니다.")
    elif resuming:
        print("ℹ️ 이미 성공한 Kinesis 100건 주입은 건너뛰고 후속 검증을 재개합니다.")
    else:
        inject_events(kinesis, events)
    if not resume_at_glue:
        show_warm_results(table, {event["service"] for event in events})
        wait_for_raw_object(s3, started_at)
    glue_started_at = datetime.now(timezone.utc)
    run_glue_job(glue)
    show_parquet_result(s3, glue_started_at)
    print("\n🎉 Warm/Cold 데이터 파이프라인 E2E 검증 완료")


if __name__ == "__main__":
    main()
