# One item per report. Partition key = build, so "all reports for a build" is
# a single Query. Sort key = "<ISO timestamp>#<id>", so the Query can return
# them newest first.
resource "aws_dynamodb_table" "reports" {
  name = var.project

  # On-demand: pay per request, nothing when idle, no capacity to tune.
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "build"
  range_key = "sk"

  # Only key attributes are declared; every other field is schemaless.
  attribute {
    name = "build"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }
}
