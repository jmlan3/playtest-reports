# Lets GitHub Actions trade the short-lived OIDC token GitHub issues to each
# workflow run for temporary AWS credentials, so no AWS keys live in GitHub.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # No thumbprint_list: AWS checks GitHub's certificate against its own
  # trusted certificate authorities, so pinned thumbprints aren't needed.
}

# Who may assume the deploy role (the trust policy).
data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    # The token must have been issued for AWS STS...
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # ...to a workflow in this repository, running either on main or for a
    # pull request. Pull requests from forks get a read-only GitHub token and
    # can't request an OIDC token at all.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values = [
        "repo:${var.github_repository}:ref:refs/heads/main",
        "repo:${var.github_repository}:pull_request",
      ]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name               = "${var.project}-github-deploy"
  description        = "Assumed by GitHub Actions in ${var.github_repository} to run Terraform on infra/"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
}

# What the deploy role may do, part 1: read and write infra/'s state file and
# its lock file. Part 2, managing infra/'s resources, is in
# deploy_permissions.tf.
data "aws_iam_policy_document" "deploy_state" {
  statement {
    sid       = "ListStateBucket"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.state.arn]
  }

  statement {
    sid       = "ReadWriteInfraState"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.state.arn}/infra/*"]
  }
}

resource "aws_iam_role_policy" "deploy_state" {
  name   = "terraform-state"
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy_state.json
}
