# Zip src/ at plan time. The zip's hash goes into source_code_hash, so the
# function's code is only redeployed when a file in src/ actually changes.
data "archive_file" "lambda" {
  type        = "zip"
  source_dir  = "${path.module}/../src"
  output_path = "${path.module}/../build/lambda.zip"

  # pytest leaves compiled .pyc files here; they differ between machines and
  # would change the hash on every run.
  excludes = ["__pycache__/**"]

  # Windows and Linux report different file permissions; fixing them keeps
  # the zip identical wherever it's built.
  output_file_mode = "0644"
}

# Created by Terraform rather than left to Lambda: a log group Lambda creates
# itself keeps logs forever and isn't managed here.
resource "aws_cloudwatch_log_group" "lambda" {
  name              = "/aws/lambda/${var.project}"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "api" {
  function_name    = var.project
  role             = aws_iam_role.lambda.arn
  runtime          = "python3.12"
  handler          = "handler.lambda_handler"
  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  # Graviton: about 20% cheaper per GB-second than x86. Safe because the code
  # is pure Python with no compiled dependencies.
  architectures = ["arm64"]
  memory_size   = 256
  timeout       = 10

  environment {
    variables = {
      TABLE_NAME            = aws_dynamodb_table.reports.name
      SECRET_PARAMETER_NAME = var.secret_parameter_name
    }
  }

  logging_config {
    log_format = "Text"
    log_group  = aws_cloudwatch_log_group.lambda.name
  }

  # The role needs its policy before the function can run.
  depends_on = [aws_iam_role_policy.lambda]
}
