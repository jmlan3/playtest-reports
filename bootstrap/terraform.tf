terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.9"
    }
  }

  # This stack creates the bucket below, so the first apply had to use local
  # state. The state was then moved into the bucket with
  # `terraform init -migrate-state`. The deploy role's access stops at infra/,
  # so CI can't read or change this state.
  backend "s3" {
    bucket       = "playtest-reports-tfstate-0b937a59"
    key          = "bootstrap/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true # lock with a .tflock object in S3, no DynamoDB table
  }
}
