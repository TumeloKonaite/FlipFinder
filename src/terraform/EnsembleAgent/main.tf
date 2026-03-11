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
  deployment_package_path = "${path.module}/lambda/ensemble_agent.zip"
  ensemble_environment = {
    DEFAULT_AWS_REGION             = var.aws_region
    BEDROCK_AWS_REGION             = var.bedrock_aws_region != "" ? var.bedrock_aws_region : var.aws_region
    PRICER_PREPROCESSOR_MODEL      = var.preprocessor_model
    FRONTIER_AGENT_LAMBDA_NAME     = var.frontier_lambda_name
    SPECIALIST_AGENT_LAMBDA_NAME   = var.specialist_lambda_name
    NN_AGENT_LAMBDA_NAME           = var.nn_lambda_name
    ENSEMBLE_REQUIRE_REMOTE_AGENTS = "true"
    ENSEMBLE_WEIGHT_FRONTIER       = tostring(var.ensemble_weight_frontier)
    ENSEMBLE_WEIGHT_SPECIALIST     = tostring(var.ensemble_weight_specialist)
    ENSEMBLE_WEIGHT_NN             = tostring(var.ensemble_weight_nn)
    PYTHONPATH                     = "/var/task:/var/task/src"
  }

  package_files = [
    "${path.root}/../../agents/EnsembleAgent/lambda_handler.py",
    "${path.root}/../../agents/EnsembleAgent/ensemble_agent.py",
    "${path.root}/../../agents/EnsembleAgent/requirements.lambda.txt",
    "${path.root}/../../agents/EnsembleAgent/preprocessor.py",
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

resource "aws_iam_role_policy" "ensemble_runtime_policy" {
  name = "${var.project_name}-runtime-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeAgentLambdas"
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = [
          var.frontier_lambda_arn,
          var.specialist_lambda_arn,
          var.nn_lambda_arn
        ]
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

resource "terraform_data" "package_ensemble_lambda" {
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

resource "aws_lambda_function" "ensemble_agent" {
  function_name    = var.lambda_function_name
  role             = aws_iam_role.lambda_execution_role.arn
  runtime          = "python3.12"
  handler          = "src.agents.EnsembleAgent.lambda_handler.lambda_handler"
  filename         = local.deployment_package_path
  source_code_hash = terraform_data.package_ensemble_lambda.output
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  architectures    = ["x86_64"]

  environment {
    variables = local.ensemble_environment
  }

  depends_on = [
    terraform_data.package_ensemble_lambda,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.ensemble_runtime_policy,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "ensemble_agent" {
  name              = "/aws/lambda/${aws_lambda_function.ensemble_agent.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}

resource "aws_lambda_function_url" "ensemble_agent" {
  count              = var.create_function_url ? 1 : 0
  function_name      = aws_lambda_function.ensemble_agent.function_name
  authorization_type = "NONE"
}

resource "aws_lambda_permission" "function_url_public" {
  count                  = var.create_function_url ? 1 : 0
  statement_id           = "AllowPublicFunctionUrlInvoke"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.ensemble_agent.function_name
  principal              = "*"
  function_url_auth_type = "NONE"
}
