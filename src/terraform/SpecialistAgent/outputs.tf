output "ecr_repository_url" {
  value = aws_ecr_repository.pricer.repository_url
}

output "sagemaker_model_name" {
  value = aws_sagemaker_model.pricer.name
}

output "sagemaker_endpoint_name" {
  value = aws_sagemaker_endpoint.pricer.name
}

output "lambda_function_name" {
  value = aws_lambda_function.pricer_wrapper.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.pricer_wrapper.arn
}

output "setup_instructions" {
  value = <<-EOT
    One-command deployment:
    1. terraform init
    2. terraform apply

    Local prerequisites:
    - Docker with buildx available as ${var.docker_executable}
    - AWS CLI available as ${var.aws_cli_executable}

    Auto-build enabled: ${var.auto_build_image}
    Image: ${aws_ecr_repository.pricer.repository_url}:${var.image_tag}

    Runtime environment variables:
    - DEFAULT_AWS_REGION=${var.aws_region}
    - SAGEMAKER_ENDPOINT_NAME=${aws_sagemaker_endpoint.pricer.name}
    - PRICER_LAMBDA_NAME=${aws_lambda_function.pricer_wrapper.function_name}
  EOT
}
