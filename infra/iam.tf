# The Lambda's execution role: what the function's code may do in AWS.

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "lambda" {
  name = "${var.project}-lambda"
  # Roles CI creates live under this path, so the deploy role's IAM
  # permissions can be limited to it.
  path               = "/${var.project}/"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json

  # The ceiling from bootstrap/. The deploy role isn't allowed to create or
  # change a role without it.
  permissions_boundary = local.workload_boundary_arn
}

data "aws_iam_policy_document" "lambda" {
  statement {
    sid       = "ReadWriteReports"
    actions   = ["dynamodb:PutItem", "dynamodb:Query"]
    resources = [aws_dynamodb_table.reports.arn]
  }

  # No kms:Decrypt: the secret uses the AWS-managed aws/ssm key, which can't
  # have access policies of its own. ssm:GetParameter alone controls access.
  statement {
    sid       = "ReadSharedSecret"
    actions   = ["ssm:GetParameter"]
    resources = [local.secret_parameter_arn]
  }

  statement {
    sid       = "WriteOwnLogs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.lambda.arn}:*"]
  }
}

resource "aws_iam_role_policy" "lambda" {
  name   = "reports-api"
  role   = aws_iam_role.lambda.id
  policy = data.aws_iam_policy_document.lambda.json
}
