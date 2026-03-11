output "deployment_package_path" {
  value = local.deployment_package_path
}

output "lambda_function_name" {
  value = aws_lambda_function.planning_agent.function_name
}

output "lambda_function_arn" {
  value = aws_lambda_function.planning_agent.arn
}

output "messaging_sns_topic_arn" {
  value = aws_sns_topic.deal_alerts.arn
}

output "setup_instructions" {
  value = <<-EOT
    Deployment is zip-based and packages automatically during terraform apply.

    First run:
    1. terraform init
    2. terraform apply

    Required downstream wiring:
    - SCANNER_AGENT_LAMBDA_NAME=${var.scanner_lambda_name}
    - ENSEMBLE_AGENT_LAMBDA_NAME=${var.ensemble_lambda_name}
    - MESSAGING_SNS_TOPIC_ARN is created by this stack
    - MESSAGING_BEDROCK_REGION=${var.messaging_bedrock_region != "" ? var.messaging_bedrock_region : var.aws_region}
    - MESSAGING_BEDROCK_MODEL_ID=${var.messaging_bedrock_model_id}
  EOT
}
