variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "scanner-agent"
}

variable "lambda_function_name" {
  type    = string
  default = "scanner-agent-runner"
}

variable "lambda_timeout" {
  type    = number
  default = 180
}

variable "lambda_memory_size" {
  type    = number
  default = 1024
}

variable "lambda_reserved_concurrency" {
  type    = number
  default = null
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "scanner_schedule_expression" {
  type    = string
  default = "rate(30 minutes)"
}

variable "scanner_memory_table_name" {
  type    = string
  default = "scanner-agent-memory"
}

variable "scanner_memory_max_items" {
  type    = number
  default = 500
}

variable "openai_api_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "openai_api_key_secret_arn" {
  type    = string
  default = ""
}

variable "python_executable" {
  type    = string
  default = "python"
}

variable "tags" {
  type    = map(string)
  default = {}
}
