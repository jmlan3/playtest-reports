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
