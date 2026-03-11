variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "project_prefix" {
  type    = string
  default = "pricing"
}

variable "log_retention_in_days" {
  type    = number
  default = 7
}

variable "tags" {
  type    = map(string)
  default = {}
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

variable "auto_build_container_images" {
  type    = bool
  default = true
}

variable "embedding_product_data_bucket_name" {
  type    = string
  default = ""
}

variable "embedding_product_data_bucket_force_destroy" {
  type    = bool
  default = false
}

variable "embedding_image_tag" {
  type    = string
  default = "latest"
}

variable "embedding_model_name" {
  type    = string
  default = "sentence-transformers/all-MiniLM-L6-v2"
}

variable "normalize_embeddings" {
  type    = bool
  default = true
}

variable "embedding_batch_size" {
  type    = number
  default = 32
}

variable "embedding_endpoint_names" {
  type    = list(string)
  default = ["flipfinder-embedding-endpoint"]
}

variable "embedding_endpoint_memory_size_in_mb" {
  type    = number
  default = 3072
}

variable "embedding_endpoint_max_concurrency" {
  type    = number
  default = 4
}

variable "nn_image_tag" {
  type    = string
  default = "latest"
}

variable "nn_lambda_timeout" {
  type    = number
  default = 120
}

variable "nn_lambda_memory_size" {
  type    = number
  default = 3008
}

variable "specialist_image_tag" {
  type    = string
  default = "latest"
}

variable "specialist_instance_type" {
  type    = string
  default = "ml.g5.xlarge"
}

variable "specialist_initial_instance_count" {
  type    = number
  default = 1
}

variable "specialist_base_model" {
  type    = string
  default = "Qwen/Qwen2.5-3B-Instruct"
}

variable "specialist_finetuned_model" {
  type = string
}

variable "specialist_model_revision" {
  type    = string
  default = ""
}

variable "huggingface_api_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "specialist_question" {
  type    = string
  default = "What does this cost to the nearest dollar?"
}

variable "specialist_prefix" {
  type    = string
  default = "Price is $"
}

variable "specialist_max_new_tokens" {
  type    = number
  default = 5
}

variable "specialist_seed" {
  type    = number
  default = 42
}

variable "specialist_lambda_timeout" {
  type    = number
  default = 180
}

variable "specialist_lambda_memory_size" {
  type    = number
  default = 256
}

variable "frontier_lambda_timeout" {
  type    = number
  default = 120
}

variable "frontier_lambda_memory_size" {
  type    = number
  default = 2048
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

variable "frontier_top_k" {
  type    = number
  default = 5
}

variable "ensemble_lambda_timeout" {
  type    = number
  default = 120
}

variable "ensemble_lambda_memory_size" {
  type    = number
  default = 1024
}

variable "create_ensemble_function_url" {
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

variable "scanner_project_name" {
  type    = string
  default = "scanner-agent"
}

variable "scanner_lambda_function_name" {
  type    = string
  default = "scanner-agent-runner"
}

variable "scanner_lambda_timeout" {
  type    = number
  default = 180
}

variable "scanner_lambda_memory_size" {
  type    = number
  default = 1024
}

variable "scanner_lambda_reserved_concurrency" {
  type    = number
  default = null
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

variable "planning_project_name" {
  type    = string
  default = "planning-agent"
}

variable "planning_lambda_function_name" {
  type    = string
  default = "planning-agent-orchestrator"
}

variable "planning_lambda_timeout" {
  type    = number
  default = 180
}

variable "planning_lambda_memory_size" {
  type    = number
  default = 1024
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
