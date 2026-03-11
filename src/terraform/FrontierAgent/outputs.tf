output "deployment_package_path" {
  value = local.deployment_package_path
}

output "lambda_function_name" {
  value = aws_lambda_function.frontier_agent.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.frontier_agent.arn
}

output "setup_instructions" {
  value = <<-EOT
    Deployment is zip-based and packages automatically during terraform apply.

    First run:
    1. terraform init
    2. terraform apply

    Runtime environment variables:
    - DEFAULT_AWS_REGION=${var.aws_region}
    - FRONTIER_AWS_REGION=${var.frontier_aws_region != "" ? var.frontier_aws_region : var.aws_region}
    - FRONTIER_VECTOR_BUCKET=${var.frontier_vector_bucket}
    - FRONTIER_INDEX_NAME=${var.frontier_index_name}
    - FRONTIER_SAGEMAKER_ENDPOINT=${var.embedding_endpoint_name}
    - FRONTIER_TOP_K=${var.frontier_top_k}
    - FRONTIER_MODEL=${var.frontier_model}
    - Optional secret sources: OPENAI_API_KEY_SECRET_ARN or OPENAI_API_KEY_SSM_PARAMETER_NAME
  EOT
}
