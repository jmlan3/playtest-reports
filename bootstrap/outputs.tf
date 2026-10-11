output "state_bucket" {
  description = "Bucket for infra/'s state. Goes in infra/backend.tf (it isn't secret)."
  value       = aws_s3_bucket.state.bucket
}

output "deploy_role_arn" {
  description = "Set as the AWS_ROLE_ARN repository variable in GitHub. Contains the account ID, so it stays out of the repo."
  value       = aws_iam_role.deploy.arn
}

output "workload_boundary_arn" {
  description = "Permissions boundary that infra/ attaches to the Lambda's role."
  value       = aws_iam_policy.workload_boundary.arn
}
