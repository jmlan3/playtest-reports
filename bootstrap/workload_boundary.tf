# A permissions boundary is a ceiling, not a grant: a role's effective
# permissions are the overlap of its own policies and its boundary.
#
# The deploy role can only create or change IAM roles that carry this
# boundary (see deploy_permissions.tf). Without that rule, anyone able to
# change a workflow could use the deploy role to create an admin role. With
# it, the worst they can create is a role limited to this project's table,
# secret and logs.
#
# It lives here, not in infra/, so the deploy role can't edit its own ceiling.
data "aws_iam_policy_document" "workload_boundary" {
  statement {
    sid = "ReportsTable"
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:DeleteItem",
      "dynamodb:Query",
    ]
    resources = ["arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.project}*"]
  }

  statement {
    sid       = "ReadProjectParameters"
    actions   = ["ssm:GetParameter"]
    resources = ["arn:aws:ssm:${local.region}:${local.account_id}:parameter/${var.project}/*"]
  }

  # No kms:Decrypt: the secret uses the AWS-managed aws/ssm key, and the
  # Lambda reads it with ssm:GetParameter alone (verified against the live
  # API).

  statement {
    sid     = "WriteOwnLogs"
    actions = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = [
      "arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.project}*:*",
    ]
  }
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "${var.project}-workload-boundary"
  description = "Permissions boundary for every IAM role the GitHub deploy role creates"
  policy      = data.aws_iam_policy_document.workload_boundary.json
}
