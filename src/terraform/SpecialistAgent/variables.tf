variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_name" {
  type    = string
  default = "pricer-service"
}

variable "image_tag" {
  type    = string
  default = "latest"
}

variable "sagemaker_endpoint_name" {
  type    = string
  default = "pricer-endpoint"
}

variable "instance_type" {
  type    = string
  default = "ml.g5.xlarge"
}

variable "initial_instance_count" {
  type    = number
  default = 1
}

variable "base_model" {
  type    = string
  default = "Qwen/Qwen2.5-3B-Instruct"
}

variable "finetuned_model" {
  type = string
}

variable "model_revision" {
  type    = string
  default = ""
}

variable "huggingface_api_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "question" {
  type    = string
  default = "What does this cost to the nearest dollar?"
}

variable "prefix" {
  type    = string
  default = "Price is $"
}

variable "max_new_tokens" {
  type    = number
  default = 5
}

variable "seed" {
  type    = number
  default = 42
}

variable "lambda_source_file" {
  type    = string
  default = "../../agents/SpecialistAgent/pricer_service.py"
}

variable "lambda_function_name" {
  type    = string
  default = "pricer-service-wrapper"
}

variable "lambda_timeout" {
  type    = number
  default = 180
}

variable "lambda_memory_size" {
  type    = number
  default = 256
}

variable "docker_executable" {
  type    = string
  default = "docker"
}

variable "aws_cli_executable" {
  type    = string
  default = "aws"
}

variable "docker_platform" {
  type    = string
  default = "linux/amd64"
}

variable "auto_build_image" {
  type    = bool
  default = true
}

variable "tags" {
  type    = map(string)
  default = {}
}
