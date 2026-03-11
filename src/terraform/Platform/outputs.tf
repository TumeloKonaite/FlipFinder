output "embedding_ecr_repository_url" {
  value = module.embedding_service.ecr_repository_url
}

output "embedding_endpoint_name" {
  value = module.embedding_service.sagemaker_endpoint_name
}

output "embedding_product_data_bucket_name" {
  value = module.embedding_service.product_data_bucket_name
}

output "nn_ecr_repository_url" {
  value = module.nn_agent.ecr_repository_url
}

output "specialist_ecr_repository_url" {
  value = module.specialist_agent.ecr_repository_url
}

output "frontier_deployment_package_path" {
  value = module.frontier_agent.deployment_package_path
}

output "ensemble_deployment_package_path" {
  value = module.ensemble_agent.deployment_package_path
}

output "scanner_deployment_package_path" {
  value = module.scanner_agent.deployment_package_path
}

output "planning_deployment_package_path" {
  value = module.planning_agent.deployment_package_path
}

output "nn_lambda_function_name" {
  value = module.nn_agent.lambda_function_name
}

output "specialist_lambda_function_name" {
  value = module.specialist_agent.lambda_function_name
}

output "frontier_lambda_function_name" {
  value = module.frontier_agent.lambda_function_name
}

output "ensemble_lambda_function_name" {
  value = module.ensemble_agent.lambda_function_name
}

output "scanner_lambda_function_name" {
  value = module.scanner_agent.lambda_function_name
}

output "planning_lambda_function_name" {
  value = module.planning_agent.lambda_function_name
}

output "ensemble_lambda_function_url" {
  value = module.ensemble_agent.lambda_function_url
}

output "messaging_sns_topic_arn" {
  value = module.planning_agent.messaging_sns_topic_arn
}

output "setup_instructions" {
  value = <<-EOT
    This stack now deploys the embedding service, NNAgent, SpecialistAgent, FrontierAgent, EnsembleAgent, ScannerAgent, and PlanningAgent in one apply.

    One-command deployment:
    1. terraform init
    2. terraform apply

    Local prerequisites:
    - Docker with buildx available on PATH
    - AWS CLI authenticated for ${var.aws_region}
    - Python available as ${var.python_executable}

    Auto-built container images:
    - Embedding -> ${module.embedding_service.ecr_repository_url}:${var.embedding_image_tag}
    - NN -> ${module.nn_agent.ecr_repository_url}:${var.nn_image_tag}
    - Specialist -> ${module.specialist_agent.ecr_repository_url}:${var.specialist_image_tag}

    Auto-wired downstream services:
    - Frontier -> ${module.frontier_agent.lambda_function_name} using embedding endpoint ${module.embedding_service.sagemaker_endpoint_name}
    - Ensemble -> ${module.ensemble_agent.lambda_function_name}
    - Scanner -> ${module.scanner_agent.lambda_function_name}
    - Planning -> ${module.planning_agent.lambda_function_name}
  EOT
}
