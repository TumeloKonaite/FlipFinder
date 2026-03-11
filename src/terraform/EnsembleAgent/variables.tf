variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "ensemble-agent"
}

variable "lambda_function_name" {
  type    = string
  default = "ensemble-agent-orchestrator"
}

variable "lambda_timeout" {
  type    = number
  default = 120
}

variable "lambda_memory_size" {
  type    = number
  default = 1024
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "create_function_url" {
  type    = bool
  default = false
}

variable "bedrock_aws_region" {
  type    = string
  default = ""
}

variable "preprocessor_model" {
  type    = string
  default = "bedrock/converse/openai.gpt-oss-120b-1:0"
}

variable "frontier_lambda_name" {
  type = string
}

variable "frontier_lambda_arn" {
  type = string
}

variable "specialist_lambda_name" {
  type = string
}

variable "specialist_lambda_arn" {
  type = string
}

variable "nn_lambda_name" {
  type = string
}

variable "nn_lambda_arn" {
  type = string
}

variable "ensemble_weight_frontier" {
  type    = number
  default = 0.8
}

variable "ensemble_weight_specialist" {
  type    = number
  default = 0.1
}

variable "ensemble_weight_nn" {
  type    = number
  default = 0.1
}

variable "python_executable" {
  type    = string
  default = "python"
}

variable "tags" {
  type    = map(string)
  default = {}
}
