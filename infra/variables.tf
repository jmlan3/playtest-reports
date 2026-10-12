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

variable "secret_parameter_name" {
  description = "SSM SecureString holding the shared secret. Created by hand, never by Terraform."
  type        = string
  default     = "/playtest-reports/shared-secret"
}

variable "log_retention_days" {
  description = "How long the Lambda's logs are kept."
  type        = number
  default     = 7
}

variable "throttle_rate_limit" {
  description = "Steady-state requests per second the API accepts before returning 429."
  type        = number
  default     = 5
}

variable "throttle_burst_limit" {
  description = "Requests the API accepts in a short burst above the steady rate."
  type        = number
  default     = 10
}
