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
    "projection.year.type"      = "date"
    "projection.year.format"    = "yyyy"
    "projection.year.range"     = "2024,2030"
    "projection.month.type"     = "date"
    "projection.month.format"   = "MM"
    "projection.month.range"    = "01,12"
    "projection.day.type"       = "date"
    "projection.day.format"     = "dd"
    "projection.day.range"      = "01,31"
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
    "projection.year.type"      = "date"
    "projection.year.format"    = "yyyy"
    "projection.year.range"     = "2024,2030"
    "projection.month.type"     = "date"
    "projection.month.format"   = "MM"
    "projection.month.range"    = "01,12"
    "projection.day.type"       = "date"
    "projection.day.format"     = "dd"
    "projection.day.range"      = "01,31"
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
