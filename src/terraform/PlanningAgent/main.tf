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

locals {
  deployment_package_path = "${path.module}/lambda/planning_agent.zip"
  planning_environment = {
    DEFAULT_AWS_REGION         = var.aws_region
    SCANNER_AGENT_LAMBDA_NAME  = var.scanner_lambda_name
    ENSEMBLE_AGENT_LAMBDA_NAME = var.ensemble_lambda_name
    MESSAGING_SNS_TOPIC_ARN    = aws_sns_topic.deal_alerts.arn
    MESSAGING_BEDROCK_REGION   = var.messaging_bedrock_region != "" ? var.messaging_bedrock_region : var.aws_region
    MESSAGING_BEDROCK_MODEL_ID = var.messaging_bedrock_model_id
    PYTHONPATH                 = "/var/task:/var/task/src"
  }

  package_files = [
    "${path.root}/../../agents/PlanningAgent/lambda_handler.py",
    "${path.root}/../../agents/PlanningAgent/requirements.lambda.txt",
    "${path.root}/../../agents/planning_agent.py",
    "${path.root}/../../agents/MessangingAgent/messaging_agent.py",
    "${path.root}/../../agents/ScannerAgent/deals.py",
    "${path.root}/../../agents/agent.py",
    "${path.root}/../../agents/__init__.py",
    "${path.root}/../../__init__.py",
    "${path.module}/package.py",
  ]
}

resource "aws_iam_role" "lambda_execution_role" {
  name = "${var.project_name}-lambda-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

resource "aws_sns_topic" "deal_alerts" {
  name = var.messaging_sns_topic_name
  tags = var.tags
}

resource "aws_sns_topic_subscription" "deal_alerts_email" {
  count     = var.messaging_email_endpoint != "" ? 1 : 0
  topic_arn = aws_sns_topic.deal_alerts.arn
  protocol  = "email"
  endpoint  = var.messaging_email_endpoint
}

resource "aws_iam_role_policy" "planning_runtime_policy" {
  name = "${var.project_name}-runtime-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeDownstreamAgentLambdas"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          var.scanner_lambda_arn,
          var.ensemble_lambda_arn,
        ]
      },
      {
        Sid    = "PublishDealNotifications"
        Effect = "Allow"
        Action = [
          "sns:Publish"
        ]
        Resource = aws_sns_topic.deal_alerts.arn
      },
      {
        Sid    = "InvokeBedrockModels"
        Effect = "Allow"
        Action = [
          "bedrock:Converse",
          "bedrock:ConverseStream",
          "bedrock:InvokeModel",
          "bedrock:InvokeModelWithResponseStream"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "terraform_data" "package_planning_lambda" {
  input = base64sha256(join("", [
    for file_path in local.package_files : filemd5(file_path)
  ]))

  triggers_replace = [
    for file_path in local.package_files : filemd5(file_path)
  ]

  provisioner "local-exec" {
    command     = "${var.python_executable} package.py"
    interpreter = ["cmd", "/c"]
    working_dir = path.module
  }
}

resource "aws_lambda_function" "planning_agent" {
  function_name    = var.lambda_function_name
  role             = aws_iam_role.lambda_execution_role.arn
  runtime          = "python3.12"
  handler          = "src.agents.PlanningAgent.lambda_handler.lambda_handler"
  filename         = local.deployment_package_path
  source_code_hash = terraform_data.package_planning_lambda.output
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  architectures    = ["x86_64"]

  environment {
    variables = local.planning_environment
  }

  depends_on = [
    terraform_data.package_planning_lambda,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.planning_runtime_policy,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "planning_agent" {
  name              = "/aws/lambda/${aws_lambda_function.planning_agent.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}
