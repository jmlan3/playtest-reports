variable "region" {
  description = "AWS region for every resource in this project."
  type        = string
  default     = "us-east-1"
}

variable "project" {
  description = "Name prefix for resources, and the Project tag."
  type        = string
  default     = "playtest-reports"
}

variable "github_repository" {
  description = "The only GitHub repository (owner/name) allowed to assume the deploy role."
  type        = string
  default     = "jmlan3/playtest-reports"
}

# Public numbers, not secrets: https://api.github.com/repos/<owner>/<name>
# returns them as owner.id and id.
variable "github_owner_id" {
  description = "Numeric ID of the repository's owner account."
  type        = string
  default     = "128272466"
}

variable "github_repository_id" {
  description = "Numeric ID of the repository."
  type        = string
  default     = "1414745494"
}
