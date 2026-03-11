variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "planning-agent"
}

variable "lambda_function_name" {
  type    = string
  default = "planning-agent-orchestrator"
}

variable "lambda_timeout" {
  type    = number
  default = 180
}

variable "lambda_memory_size" {
  type    = number
  default = 1024
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "scanner_lambda_name" {
  type = string
}

variable "scanner_lambda_arn" {
  type = string
}

variable "ensemble_lambda_name" {
  type = string
}

variable "ensemble_lambda_arn" {
  type = string
}

variable "messaging_sns_topic_name" {
  type    = string
  default = "deal-alerts"
}

variable "messaging_email_endpoint" {
  type    = string
  default = ""
}

variable "messaging_bedrock_region" {
  type    = string
  default = ""
}

variable "messaging_bedrock_model_id" {
  type    = string
  default = "amazon.nova-micro-v1:0"
}

variable "python_executable" {
  type    = string
  default = "python"
}

variable "tags" {
  type    = map(string)
  default = {}
}
