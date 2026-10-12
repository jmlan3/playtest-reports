terraform {
  required_version = "~> 1.16"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.68"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.8"
    }
  }

  # State lives in the bucket bootstrap/ created. The deploy role can read
  # and write keys under infra/ only.
  backend "s3" {
    bucket       = "playtest-reports-tfstate-0b937a59"
    key          = "infra/terraform.tfstate"
    region       = "us-east-1"
    encrypt      = true
    use_lockfile = true # lock with a .tflock object in S3, no DynamoDB table
  }
}
