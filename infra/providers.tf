provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      Stack     = "infra"
      ManagedBy = "terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  # Looked up at plan time so the account ID never has to be written in the repo.
  account_id = data.aws_caller_identity.current.account_id
  region     = data.aws_region.current.region

  # Built from names rather than looked up: reading the parameter with a data
  # source would copy the decrypted secret into Terraform state, and the deploy
  # role can't read bootstrap/'s state to look up the boundary.
  secret_parameter_arn  = "arn:aws:ssm:${local.region}:${local.account_id}:parameter${var.secret_parameter_name}"
  workload_boundary_arn = "arn:aws:iam::${local.account_id}:policy/${var.project}-workload-boundary"
}
