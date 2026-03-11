output "ecr_repository_url" {
  value = aws_ecr_repository.nn_agent.repository_url
}

output "lambda_function_name" {
  value = aws_lambda_function.nn_agent.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.nn_agent.arn
}

output "setup_instructions" {
  value = <<-EOT
    This module deploys NNAgent as an AWS Lambda container image for the ensemble.

    One-command deployment:
    1. terraform init
    2. terraform apply

    Local prerequisites:
    - Docker with buildx available as ${var.docker_executable}
    - AWS CLI available as ${var.aws_cli_executable}

    Auto-build enabled: ${var.auto_build_image}
    Image: ${aws_ecr_repository.nn_agent.repository_url}:${var.image_tag}
  EOT
}
