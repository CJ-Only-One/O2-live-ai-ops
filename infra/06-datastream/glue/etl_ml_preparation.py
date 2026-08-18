"""Raw 이벤트를 AI 학습용 Parquet 데이터셋으로 변환하는 Glue 배치 작업."""

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext
from pyspark.sql import functions as F
from pyspark.sql.utils import AnalysisException


RAW_INPUT_PATHS = [
    "s3://o2-data-lake-066107819912/raw/business/",
    "s3://o2-data-lake-066107819912/raw/client/",
]
ML_READY_OUTPUT_PATH = "s3://o2-data-lake-066107819912/ml-ready/"


def main() -> None:
    """Glue 작업을 초기화하고 Raw JSON을 파티션된 Parquet으로 변환한다."""
    args = getResolvedOptions(sys.argv, ["JOB_NAME"])
    glue_context = GlueContext(SparkContext.getOrCreate())
    spark = glue_context.spark_session

    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    # text reader도 파일별 GZIP 코덱을 자동 해제한다. JSON 원문에서 필요한 값만
    # 추출하면 서로 다른 payload 스키마나 타입 충돌의 영향을 받지 않는다.
    input_frames = []
    for input_path in RAW_INPUT_PATHS:
        try:
            input_frames.append(spark.read.text(input_path))
        except AnalysisException:
            # 아직 이벤트가 한 번도 도착하지 않은 prefix는 S3에 존재하지 않는다.
            print(f"[warn] 입력 경로가 없어 건너뜁니다: {input_path}")
    if not input_frames:
        raise RuntimeError("읽을 수 있는 Raw 입력 경로가 없습니다.")

    raw_df = input_frames[0]
    for input_frame in input_frames[1:]:
        raw_df = raw_df.unionByName(input_frame)
    json_value = F.col("value")
    event_ts = F.get_json_object(json_value, "$.event_ts")
    event_timestamp = F.to_timestamp(event_ts)

    ml_ready_df = raw_df.select(
        F.get_json_object(json_value, "$.event_id").alias("event_id"),
        F.get_json_object(json_value, "$.event_name").alias("event_name"),
        event_ts.alias("event_ts"),
        F.get_json_object(json_value, "$.service").alias("service"),
        F.get_json_object(json_value, "$.service_version").alias("service_version"),
        F.get_json_object(json_value, "$.trace_id").alias("trace_id"),
        # payload 객체는 평탄화하지 않고 유효한 JSON 문자열 그대로 저장한다.
        F.get_json_object(json_value, "$.payload").alias("payload"),
        F.year(event_timestamp).alias("year"),
        F.month(event_timestamp).alias("month"),
        F.dayofmonth(event_timestamp).alias("day"),
    )

    # 요구된 일일 전체 재생성 방식으로 날짜 파티션을 덮어쓴다.
    (
        ml_ready_df.write.mode("overwrite")
        .partitionBy("year", "month", "day")
        .parquet(ML_READY_OUTPUT_PATH)
    )

    job.commit()


if __name__ == "__main__":
    main()
