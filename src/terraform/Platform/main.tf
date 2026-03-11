terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  embedding_product_data_bucket_name = var.embedding_product_data_bucket_name != "" ? var.embedding_product_data_bucket_name : "${var.project_prefix}-product-data-${data.aws_caller_identity.current.account_id}"
  common_tags = merge(
    {
      Stack = "PricingPlatform"
    },
    var.tags
  )
}

module "embedding_service" {
  source = "../FrontierAgent/embedding"

  aws_region                        = var.aws_region
  project_name                      = "${var.project_prefix}-embedding-service"
  product_data_bucket_name          = local.embedding_product_data_bucket_name
  product_data_bucket_force_destroy = var.embedding_product_data_bucket_force_destroy
  image_tag                         = var.embedding_image_tag
  embedding_model_name              = var.embedding_model_name
  huggingface_api_token             = var.huggingface_api_token
  normalize_embeddings              = var.normalize_embeddings
  embedding_batch_size              = var.embedding_batch_size
  embedding_endpoint_names          = var.embedding_endpoint_names
  endpoint_memory_size_in_mb        = var.embedding_endpoint_memory_size_in_mb
  endpoint_max_concurrency          = var.embedding_endpoint_max_concurrency
  docker_executable                 = var.docker_executable
  aws_cli_executable                = var.aws_cli_executable
  docker_platform                   = var.docker_platform
  auto_build_image                  = var.auto_build_container_images
  tags                              = local.common_tags
}

module "nn_agent" {
  source = "../NNAgent"

  aws_region            = var.aws_region
  project_name          = "${var.project_prefix}-nn-agent"
  lambda_function_name  = "${var.project_prefix}-nn-agent-pricer"
  image_tag             = var.nn_image_tag
  lambda_timeout        = var.nn_lambda_timeout
  lambda_memory_size    = var.nn_lambda_memory_size
  nn_weights_drive_folder_url = var.nn_weights_drive_folder_url
  log_retention_in_days = var.log_retention_in_days
  docker_executable     = var.docker_executable
  aws_cli_executable    = var.aws_cli_executable
  docker_platform       = var.docker_platform
  auto_build_image      = var.auto_build_container_images
  tags                  = local.common_tags
}

module "specialist_agent" {
  source = "../SpecialistAgent"

  aws_region              = var.aws_region
  project_name            = "${var.project_prefix}-specialist-agent"
  image_tag               = var.specialist_image_tag
  sagemaker_endpoint_name = "${var.project_prefix}-specialist-endpoint"
  instance_type           = var.specialist_instance_type
  initial_instance_count  = var.specialist_initial_instance_count
  base_model              = var.specialist_base_model
  finetuned_model         = var.specialist_finetuned_model
  model_revision          = var.specialist_model_revision
  huggingface_api_token   = var.huggingface_api_token
  question                = var.specialist_question
  prefix                  = var.specialist_prefix
  max_new_tokens          = var.specialist_max_new_tokens
  seed                    = var.specialist_seed
  lambda_function_name    = "${var.project_prefix}-specialist-wrapper"
  lambda_timeout          = var.specialist_lambda_timeout
  lambda_memory_size      = var.specialist_lambda_memory_size
  docker_executable       = var.docker_executable
  aws_cli_executable      = var.aws_cli_executable
  docker_platform         = var.docker_platform
  auto_build_image        = var.auto_build_container_images
  tags                    = local.common_tags
}

module "frontier_agent" {
  source = "../FrontierAgent"

  aws_region                        = var.aws_region
  project_name                      = "${var.project_prefix}-frontier-agent"
  lambda_function_name              = "${var.project_prefix}-frontier-agent-pricer"
  lambda_timeout                    = var.frontier_lambda_timeout
  lambda_memory_size                = var.frontier_lambda_memory_size
  log_retention_in_days             = var.log_retention_in_days
  openai_api_key                    = var.openai_api_key
  openai_api_key_secret_arn         = var.openai_api_key_secret_arn
  openai_api_key_ssm_parameter_name = var.openai_api_key_ssm_parameter_name
  frontier_model                    = var.frontier_model
  frontier_aws_region               = var.frontier_aws_region
  frontier_vector_bucket            = var.frontier_vector_bucket
  frontier_index_name               = var.frontier_index_name
  embedding_endpoint_name           = module.embedding_service.sagemaker_endpoint_name
  frontier_top_k                    = var.frontier_top_k
  python_executable                 = var.python_executable
  tags                              = local.common_tags
}

module "ensemble_agent" {
  source = "../EnsembleAgent"

  aws_region                 = var.aws_region
  project_name               = "${var.project_prefix}-ensemble-agent"
  lambda_function_name       = "${var.project_prefix}-ensemble-orchestrator"
  lambda_timeout             = var.ensemble_lambda_timeout
  lambda_memory_size         = var.ensemble_lambda_memory_size
  log_retention_in_days      = var.log_retention_in_days
  create_function_url        = var.create_ensemble_function_url
  bedrock_aws_region         = var.bedrock_aws_region
  preprocessor_model         = var.preprocessor_model
  frontier_lambda_name       = module.frontier_agent.lambda_function_name
  frontier_lambda_arn        = module.frontier_agent.lambda_function_arn
  specialist_lambda_name     = module.specialist_agent.lambda_function_name
  specialist_lambda_arn      = module.specialist_agent.lambda_function_arn
  nn_lambda_name             = module.nn_agent.lambda_function_name
  nn_lambda_arn              = module.nn_agent.lambda_function_arn
  ensemble_weight_frontier   = var.ensemble_weight_frontier
  ensemble_weight_specialist = var.ensemble_weight_specialist
  ensemble_weight_nn         = var.ensemble_weight_nn
  python_executable          = var.python_executable
  tags                       = local.common_tags
}

module "scanner_agent" {
  source = "../ScannerAgent"

  aws_region                  = var.aws_region
  project_name                = var.scanner_project_name
  lambda_function_name        = var.scanner_lambda_function_name
  lambda_timeout              = var.scanner_lambda_timeout
  lambda_memory_size          = var.scanner_lambda_memory_size
  lambda_reserved_concurrency = var.scanner_lambda_reserved_concurrency
  log_retention_in_days       = var.log_retention_in_days
  scanner_schedule_expression = var.scanner_schedule_expression
  scanner_memory_table_name   = var.scanner_memory_table_name
  scanner_memory_max_items    = var.scanner_memory_max_items
  openai_api_key              = var.openai_api_key
  openai_api_key_secret_arn   = var.openai_api_key_secret_arn
  python_executable           = var.python_executable
  tags                        = local.common_tags
}

module "planning_agent" {
  source = "../PlanningAgent"

  aws_region                 = var.aws_region
  project_name               = var.planning_project_name
  lambda_function_name       = var.planning_lambda_function_name
  lambda_timeout             = var.planning_lambda_timeout
  lambda_memory_size         = var.planning_lambda_memory_size
  log_retention_in_days      = var.log_retention_in_days
  scanner_lambda_name        = module.scanner_agent.lambda_function_name
  scanner_lambda_arn         = module.scanner_agent.lambda_function_arn
  ensemble_lambda_name       = module.ensemble_agent.lambda_function_name
  ensemble_lambda_arn        = module.ensemble_agent.lambda_function_arn
  messaging_sns_topic_name   = var.messaging_sns_topic_name
  messaging_email_endpoint   = var.messaging_email_endpoint
  messaging_bedrock_region   = var.messaging_bedrock_region
  messaging_bedrock_model_id = var.messaging_bedrock_model_id
  python_executable          = var.python_executable
  tags                       = local.common_tags
}
