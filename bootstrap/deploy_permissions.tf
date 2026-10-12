# What the deploy role may do, part 2: manage infra/'s resources.
#
# Generated with IAM Policy Autopilot from three plans of infra/ (create,
# update and destroy), then hardened by hand:
#   - scoped to this project's resource names instead of "*"
#   - IAM changes only on roles under the /playtest-reports/ path, and only
#     if the role carries the workload boundary
#   - PassRole only for those roles, and only to Lambda
#   - actions for features this project doesn't use removed (DynamoDB
#     replicas/imports and item reads/writes, Lambda code signing, KMS, ...)
# If CI fails with AccessDenied after infra/ gains a new resource type, add
# the missing action here and re-apply bootstrap locally.

locals {
  workload_roles = "arn:aws:iam::${local.account_id}:role/${var.project}/*"
}

data "aws_iam_policy_document" "deploy_infra" {
  # API Gateway's IAM actions are HTTP verbs on resource paths. An HTTP API's
  # ID is generated at creation, so this covers every HTTP API in the region
  # (not REST APIs, custom domains or account settings).
  statement {
    sid     = "HttpApis"
    actions = ["apigateway:GET", "apigateway:POST", "apigateway:PUT", "apigateway:PATCH", "apigateway:DELETE"]
    resources = [
      "arn:aws:apigateway:${local.region}::/apis",
      "arn:aws:apigateway:${local.region}::/apis/*",
      "arn:aws:apigateway:${local.region}::/tags/*",
    ]
  }

  # The table's settings only. No item reads or writes: CI never needs to
  # see the reports.
  statement {
    sid = "ReportsTable"
    actions = [
      "dynamodb:CreateTable",
      "dynamodb:DeleteTable",
      "dynamodb:DescribeContinuousBackups",
      "dynamodb:DescribeTable",
      "dynamodb:DescribeTimeToLive",
      "dynamodb:ListTagsOfResource",
      "dynamodb:TagResource",
      "dynamodb:UntagResource",
      "dynamodb:UpdateContinuousBackups",
      "dynamodb:UpdateTable",
      "dynamodb:UpdateTimeToLive",
    ]
    resources = ["arn:aws:dynamodb:${local.region}:${local.account_id}:table/${var.project}*"]
  }

  statement {
    sid = "Function"
    actions = [
      "lambda:AddPermission",
      "lambda:CreateFunction",
      "lambda:DeleteFunction",
      "lambda:DeleteFunctionConcurrency",
      "lambda:GetFunction",
      "lambda:GetFunctionCodeSigningConfig",
      "lambda:GetFunctionConcurrency",
      "lambda:GetFunctionConfiguration",
      "lambda:GetPolicy",
      "lambda:ListTags",
      "lambda:ListVersionsByFunction",
      "lambda:RemovePermission",
      "lambda:TagResource",
      "lambda:UntagResource",
      "lambda:UpdateFunctionCode",
      "lambda:UpdateFunctionConfiguration",
    ]
    resources = ["arn:aws:lambda:${local.region}:${local.account_id}:function:${var.project}*"]
  }

  # CreateFunction checks this when layers are attached. None are, but it's
  # listed as part of the operation and is read-only.
  statement {
    sid       = "ReadLayers"
    actions   = ["lambda:GetLayerVersion"]
    resources = ["arn:aws:lambda:${local.region}:${local.account_id}:layer:*:*"]
  }

  statement {
    sid = "FunctionLogGroup"
    actions = [
      "logs:CreateLogGroup",
      "logs:DeleteLogGroup",
      "logs:DeleteRetentionPolicy",
      "logs:ListTagsForResource",
      "logs:PutRetentionPolicy",
      "logs:TagLogGroup",
      "logs:TagResource",
      "logs:UntagResource",
    ]
    resources = ["arn:aws:logs:${local.region}:${local.account_id}:log-group:/aws/lambda/${var.project}*"]
  }

  # DescribeLogGroups doesn't support resource-level permissions.
  statement {
    sid       = "FindLogGroups"
    actions   = ["logs:DescribeLogGroups"]
    resources = ["*"]
  }

  statement {
    sid = "ReadWorkloadRoles"
    actions = [
      "iam:GetRole",
      "iam:GetRolePolicy",
      "iam:ListAttachedRolePolicies",
      "iam:ListInstanceProfilesForRole",
      "iam:ListRolePolicies",
      "iam:ListRoleTags",
      "iam:TagRole",
      "iam:UntagRole",
    ]
    resources = [local.workload_roles]
  }

  # The privilege-escalation guard. Every action that creates a role or
  # changes what it can do requires the role to carry the workload boundary,
  # so CI can't create a role more powerful than the boundary allows.
  # iam:DeleteRolePermissionsBoundary is deliberately not allowed.
  statement {
    sid = "ChangeWorkloadRolesOnlyWithBoundary"
    actions = [
      "iam:AttachRolePolicy",
      "iam:CreateRole",
      "iam:DeleteRole",
      "iam:DeleteRolePolicy",
      "iam:DetachRolePolicy",
      "iam:PutRolePolicy",
      "iam:UpdateAssumeRolePolicy",
      "iam:UpdateRole",
    ]
    resources = [local.workload_roles]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.workload_boundary.arn]
    }
  }

  # Handing a role to Lambda is what lets the function run with it. Limiting
  # PassRole to workload roles, and to Lambda, stops CI from attaching some
  # other, more powerful role in the account to a function.
  statement {
    sid       = "PassWorkloadRolesToLambda"
    actions   = ["iam:PassRole"]
    resources = [local.workload_roles]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role_policy" "deploy_infra" {
  name   = "terraform-infra"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_infra.json
}
