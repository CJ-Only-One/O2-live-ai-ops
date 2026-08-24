###############################################################################
# Athena & Glue Data Catalog (s3/raw 데이터 연결)
###############################################################################

# 1. Glue Catalog Database
resource "aws_glue_catalog_database" "data_lake" {
  name        = "o2_data_lake"
  description = "O2 Live Commerce Data Lake Database for Athena Querying"
}

# 2. Raw Business Events External Table (s3://o2-data-lake-066107819912/raw/business/)
resource "aws_glue_catalog_table" "raw_business" {
  name          = "raw_business"
  database_name = aws_glue_catalog_database.data_lake.name
  description   = "Raw business transaction events stored in JSON format"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "json"
    "compressionType"           = "gzip"
    "typeOfData"                = "file"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2024,2030"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "projection.hour.type"      = "integer"
    "projection.hour.range"     = "0,23"
    "projection.hour.digits"    = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.data_lake.bucket}/raw/business/year=$${year}/month=$${month}/day=$${day}/hour=$${hour}"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.bucket}/raw/business/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json_serde"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "event_name"
      type = "string"
    }
    columns {
      name = "event_ts"
      type = "string"
    }
    columns {
      name = "service"
      type = "string"
    }
    columns {
      name = "service_version"
      type = "string"
    }
    columns {
      name = "user_key"
      type = "string"
    }
    columns {
      name = "client_ip_key"
      type = "string"
    }
    columns {
      name = "broadcast_id"
      type = "string"
    }
    columns {
      name = "payload"
      type = "string"
    }
  }
}

# 3. Raw Client Events External Table (s3://o2-data-lake-066107819912/raw/client/)
resource "aws_glue_catalog_table" "raw_client" {
  name          = "raw_client"
  database_name = aws_glue_catalog_database.data_lake.name
  description   = "Raw client action events stored in JSON format"
  table_type    = "EXTERNAL_TABLE"

  parameters = {
    "classification"            = "json"
    "compressionType"           = "gzip"
    "typeOfData"                = "file"
    "projection.enabled"        = "true"
    "projection.year.type"      = "integer"
    "projection.year.range"     = "2024,2030"
    "projection.month.type"     = "integer"
    "projection.month.range"    = "1,12"
    "projection.month.digits"   = "2"
    "projection.day.type"       = "integer"
    "projection.day.range"      = "1,31"
    "projection.day.digits"     = "2"
    "projection.hour.type"      = "integer"
    "projection.hour.range"     = "0,23"
    "projection.hour.digits"    = "2"
    "storage.location.template" = "s3://${aws_s3_bucket.data_lake.bucket}/raw/client/year=$${year}/month=$${month}/day=$${day}/hour=$${hour}"
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
  partition_keys {
    name = "hour"
    type = "string"
  }

  storage_descriptor {
    location      = "s3://${aws_s3_bucket.data_lake.bucket}/raw/client/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.HiveIgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json_serde"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "event_id"
      type = "string"
    }
    columns {
      name = "event_name"
      type = "string"
    }
    columns {
      name = "event_ts"
      type = "string"
    }
    columns {
      name = "service"
      type = "string"
    }
    columns {
      name = "service_version"
      type = "string"
    }
    columns {
      name = "user_key"
      type = "string"
    }
    columns {
      name = "client_ip_key"
      type = "string"
    }
    columns {
      name = "broadcast_id"
      type = "string"
    }
    columns {
      name = "payload"
      type = "string"
    }
  }
}

# 4. Athena Primary Workgroup Result Location Setting
resource "aws_athena_workgroup" "primary" {
  name = "primary"

  configuration {
    enforce_workgroup_configuration    = false
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${aws_s3_bucket.data_lake.bucket}/athena-results/"
    }
  }

  force_destroy = false
}


###############################################################################
# 5. 카나리를 뺀 비즈니스 이벤트 뷰 (business_events)
#
# **이것은 D-052 가 명시한 대가를 갚는 자리다.** 파이프라인 생존 카나리는
# 1분마다 `stream-business` 에 합성 레코드를 하나 넣는다. 경로가 살아 있음을
# 증명하려면 그 경로로 실제로 무언가를 보내는 수밖에 없고, 그러면 Firehose 가
# 같은 스트림을 읽으므로 **합성 레코드가 S3 데이터 레이크에도 적재된다.**
#
# 그대로 두면 Athena 집계에 하루 1,440건의 가짜 이벤트가 섞인다. 건수 자체는
# 작지만 문제는 크기가 아니다 — 명세 §08 의 *"주입은 Agent 가 읽는 저장소에
# 흔적을 남기지 않는다"* 를 깬다. 에이전트가 사후 분석에서 `service` 별
# 분포를 보면 존재하지 않는 서비스가 하나 늘어 있고, 그것이 무엇인지 알
# 방법이 없다.
#
# **왜 뷰인가 — 규약이 아니라 기본값이어야 하기 때문이다.** "쿼리에 필터를
# 넣기로 한다" 는 규약은 반드시 한 번은 빠뜨려진다. 빠뜨렸을 때 오류가 아니라
# **조금 틀린 답**이 나오는 종류라 더 나쁘다. 기본으로 읽는 대상을 카나리가
# 없는 것으로 바꾸면, 필터를 빠뜨리는 실수 자체가 성립하지 않는다.
#
# `raw_business` 는 그대로 둔다. 카나리가 정말로 적재되고 있는지 확인해야 할
# 때(생존 감시를 의심할 때)는 원본을 봐야 한다.
#
# **`IS DISTINCT FROM` 을 쓴 이유** — `service <> '...'` 는 `service` 가 NULL 인
# 행에서 NULL 로 평가되어 그 행이 **조용히 사라진다.** 봉투에 service 가 없는
# 이벤트는 정상이 아니지만, 그것이 사라져 버리면 이상한 데이터가 있다는 것
# 자체를 못 본다. 카나리만 빼고 나머지는 전부 남긴다.
###############################################################################

locals {
  # 뷰의 열 = raw_business 의 데이터 열 + 파티션 키. 원본을 그대로 대신할 수
  # 있어야 한다 — 열이 빠지면 "뷰로 바꿨더니 쿼리가 깨진다" 가 되고,
  # 그러면 사람들은 원본으로 돌아간다.
  business_view_columns = [
    "event_id", "event_name", "event_ts", "service", "service_version",
    "user_key", "client_ip_key", "broadcast_id", "payload",
    "year", "month", "day", "hour",
  ]

  business_view_sql = format(
    "SELECT %s FROM %s.%s WHERE service IS DISTINCT FROM '%s'",
    join(", ", local.business_view_columns),
    aws_glue_catalog_database.data_lake.name,
    aws_glue_catalog_table.raw_business.name,
    local.canary_service,
  )
}

resource "aws_glue_catalog_table" "business_events" {
  name          = "business_events"
  database_name = aws_glue_catalog_database.data_lake.name
  description   = "비즈니스 이벤트 — 파이프라인 카나리(${local.canary_service}) 제외. 기본으로 이걸 읽는다."
  table_type    = "VIRTUAL_VIEW"

  parameters = {
    presto_view = "true"
    comment     = "Presto View"
  }

  # Athena 는 뷰 정의를 이 base64 JSON 에서 읽는다. storage_descriptor 의
  # columns 는 카탈로그(글루 콘솔·`SHOW COLUMNS`)용 사본이라 **둘이 어긋나면
  # 조회 결과와 스키마 표시가 갈린다.** 그래서 양쪽 다 같은 local 에서 만든다.
  view_original_text = "/* Presto View: ${base64encode(jsonencode({
    originalSql  = local.business_view_sql
    catalog      = "awsdatacatalog"
    schema       = aws_glue_catalog_database.data_lake.name
    columns      = [for c in local.business_view_columns : { name = c, type = "varchar" }]
    owner        = "hadoop"
    runAsInvoker = false
  }))} */"
  view_expanded_text = "/* Presto View */"

  storage_descriptor {
    ser_de_info {
      name = "json_serde"
    }

    dynamic "columns" {
      for_each = local.business_view_columns
      content {
        name = columns.value
        type = "string"
      }
    }
  }
}

###############################################################################
# 6. 저장 쿼리 — 에이전트·사람이 복사해 쓰는 기준 쿼리
#
# 뷰가 있어도 누군가는 `raw_business` 를 직접 친다. 그때 무엇을 빼야 하는지
# 여기 한 번 적어 두면, 최소한 찾아볼 곳이 생긴다.
###############################################################################

resource "aws_athena_named_query" "business_events_recent" {
  name        = "business_events_recent"
  database    = aws_glue_catalog_database.data_lake.name
  workgroup   = "primary"
  description = "최근 비즈니스 이벤트 — 카나리 제외(business_events 뷰 사용)"
  query       = <<-SQL
    -- 카나리 제외는 뷰가 이미 한다. raw_business 를 직접 읽지 않는다.
    SELECT service, event_name, count(*) AS n
    FROM ${aws_glue_catalog_database.data_lake.name}.${aws_glue_catalog_table.business_events.name}
    WHERE year  = date_format(current_date, '%Y')
      AND month = date_format(current_date, '%m')
      AND day   = date_format(current_date, '%d')
    GROUP BY service, event_name
    ORDER BY n DESC
  SQL
}

output "business_events_view_name" {
  description = <<-EOT
    카나리를 뺀 비즈니스 이벤트 뷰의 이름. **에이전트와 사후 분석은 원본
    (`raw_business`)이 아니라 이쪽을 읽는다.**
  EOT
  value       = "${aws_glue_catalog_database.data_lake.name}.${aws_glue_catalog_table.business_events.name}"
}
