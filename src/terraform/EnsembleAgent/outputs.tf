output "deployment_package_path" {
  value = local.deployment_package_path
}

output "lambda_function_name" {
  value = aws_lambda_function.ensemble_agent.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.ensemble_agent.arn
}

output "lambda_function_url" {
  value = var.create_function_url ? aws_lambda_function_url.ensemble_agent[0].function_url : null
}

output "setup_instructions" {
  value = <<-EOT
    Deployment is zip-based and packages automatically during terraform apply.

    First run:
    1. terraform init
    2. terraform apply

    Required downstream wiring:
    - FRONTIER_AGENT_LAMBDA_NAME=${var.frontier_lambda_name}
    - SPECIALIST_AGENT_LAMBDA_NAME=${var.specialist_lambda_name}
    - NN_AGENT_LAMBDA_NAME=${var.nn_lambda_name}
    - PRICER_PREPROCESSOR_MODEL=${var.preprocessor_model}
  EOT
}
