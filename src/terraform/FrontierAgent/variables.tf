variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "frontier-agent"
}

variable "lambda_function_name" {
  type    = string
  default = "frontier-agent-pricer"
}

variable "lambda_timeout" {
  type    = number
  default = 120
}

variable "lambda_memory_size" {
  type    = number
  default = 2048
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "openai_api_key_secret_arn" {
  type    = string
  default = ""
}

variable "openai_api_key_ssm_parameter_name" {
  type    = string
  default = ""
}

variable "frontier_model" {
  type    = string
  default = "gpt-5.1"
}

variable "frontier_aws_region" {
  type    = string
  default = ""
}

variable "frontier_vector_bucket" {
  type    = string
  default = "products-vectors-194722416872"
}

variable "frontier_index_name" {
  type    = string
  default = "products"
}

variable "embedding_endpoint_name" {
  type    = string
  default = "flipfinder-embedding-endpoint"
}

variable "frontier_top_k" {
  type    = number
  default = 5
}

variable "python_executable" {
  type    = string
  default = "python"
}

variable "tags" {
  type    = map(string)
  default = {}
}
