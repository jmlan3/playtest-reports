provider "aws" {
  region = var.region

  # Added to every resource that supports tags, so the console and the bill
  # show what belongs to this project and which stack manages it.
  default_tags {
    tags = {
      Project   = var.project
      Stack     = "bootstrap"
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
}
