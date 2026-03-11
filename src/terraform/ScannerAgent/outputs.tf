output "deployment_package_path" {
  value = local.deployment_package_path
}

output "lambda_function_name" {
  value = aws_lambda_function.scanner_agent.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.scanner_agent.arn
}

output "scanner_memory_table_name" {
  value = aws_dynamodb_table.scanner_memory.name
}

output "scanner_schedule_rule_name" {
  value = aws_cloudwatch_event_rule.scanner_schedule.name
}

output "setup_instructions" {
  value = <<-EOT
    Deployment is zip-based and packages automatically during terraform apply.

    First run:
    1. terraform init
    2. terraform apply

    Required runtime environment variables:
    - Preferred: OPENAI_API_KEY_SECRET_ARN via terraform.tfvars
    - Fallback: TF_VAR_openai_api_key
    - DEFAULT_AWS_REGION=${var.aws_region}

    Scheduled trigger:
    - ${var.scanner_schedule_expression}
  EOT
}
