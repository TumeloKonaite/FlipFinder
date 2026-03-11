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
  deployment_package_path = "${path.module}/lambda/scanner_agent.zip"
  scanner_environment = merge(
    {
      DEFAULT_AWS_REGION       = var.aws_region
      SCANNER_MEMORY_TABLE     = aws_dynamodb_table.scanner_memory.name
      SCANNER_MEMORY_MAX_ITEMS = tostring(var.scanner_memory_max_items)
      PYTHONPATH               = "/var/task:/var/task/src"
    },
    var.openai_api_key_secret_arn != "" ? {
      OPENAI_API_KEY_SECRET_ARN = var.openai_api_key_secret_arn
    } : {},
    var.openai_api_key != "" ? {
      OPENAI_API_KEY = var.openai_api_key
    } : {}
  )
  scanner_runtime_policy_statements = concat(
    [
      {
        Sid    = "ScannerMemoryTableAccess"
        Effect = "Allow"
        Action = [
          "dynamodb:BatchWriteItem",
          "dynamodb:DescribeTable",
          "dynamodb:PutItem",
          "dynamodb:Scan"
        ]
        Resource = aws_dynamodb_table.scanner_memory.arn
      }
    ],
    var.openai_api_key_secret_arn != "" ? [
      {
        Sid    = "ReadOpenAIKeyFromSecretsManager"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = var.openai_api_key_secret_arn
      }
    ] : []
  )

  package_files = [
    "${path.root}/../../agents/ScannerAgent/deals.py",
    "${path.root}/../../agents/ScannerAgent/scanner_agent.py",
    "${path.root}/../../agents/ScannerAgent/lambda_handler.py",
    "${path.root}/../../agents/ScannerAgent/requirements.lambda.txt",
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

resource "aws_iam_role_policy" "scanner_runtime_policy" {
  name = "${var.project_name}-runtime-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.scanner_runtime_policy_statements
  })
}

resource "aws_dynamodb_table" "scanner_memory" {
  name         = var.scanner_memory_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "url"

  attribute {
    name = "url"
    type = "S"
  }

  tags = var.tags
}

resource "terraform_data" "package_scanner_lambda" {
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

resource "aws_lambda_function" "scanner_agent" {
  function_name                  = var.lambda_function_name
  role                           = aws_iam_role.lambda_execution_role.arn
  runtime                        = "python3.12"
  handler                        = "src.agents.ScannerAgent.lambda_handler.lambda_handler"
  filename                       = local.deployment_package_path
  source_code_hash               = terraform_data.package_scanner_lambda.output
  timeout                        = var.lambda_timeout
  memory_size                    = var.lambda_memory_size
  reserved_concurrent_executions = var.lambda_reserved_concurrency
  architectures                  = ["x86_64"]

  environment {
    variables = local.scanner_environment
  }

  depends_on = [
    terraform_data.package_scanner_lambda,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.scanner_runtime_policy,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "scanner_agent" {
  name              = "/aws/lambda/${aws_lambda_function.scanner_agent.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}

resource "aws_cloudwatch_event_rule" "scanner_schedule" {
  name                = "${var.project_name}-schedule"
  description         = "Scheduled trigger for ScannerAgent deal scans"
  schedule_expression = var.scanner_schedule_expression
  tags                = var.tags
}

resource "aws_cloudwatch_event_target" "scanner_lambda" {
  rule      = aws_cloudwatch_event_rule.scanner_schedule.name
  target_id = "scanner-agent-lambda"
  arn       = aws_lambda_function.scanner_agent.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.scanner_agent.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.scanner_schedule.arn
}
