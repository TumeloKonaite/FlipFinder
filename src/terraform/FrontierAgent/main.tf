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

data "aws_caller_identity" "current" {}

locals {
  deployment_package_path = "${path.module}/lambda/frontier_agent.zip"
  frontier_environment = merge(
    {
      DEFAULT_AWS_REGION          = var.aws_region
      FRONTIER_AWS_REGION         = var.frontier_aws_region != "" ? var.frontier_aws_region : var.aws_region
      FRONTIER_VECTOR_BUCKET      = var.frontier_vector_bucket
      FRONTIER_INDEX_NAME         = var.frontier_index_name
      FRONTIER_SAGEMAKER_ENDPOINT = var.embedding_endpoint_name
      FRONTIER_TOP_K              = tostring(var.frontier_top_k)
      FRONTIER_MODEL              = var.frontier_model
      PYTHONPATH                  = "/var/task:/var/task/src"
    },
    var.openai_api_key_secret_arn != "" ? {
      OPENAI_API_KEY_SECRET_ARN = var.openai_api_key_secret_arn
    } : {},
    var.openai_api_key_ssm_parameter_name != "" ? {
      OPENAI_API_KEY_SSM_PARAMETER_NAME = var.openai_api_key_ssm_parameter_name
    } : {},
    var.openai_api_key != "" ? {
      OPENAI_API_KEY = var.openai_api_key
    } : {}
  )
  frontier_runtime_policy_statements = concat(
    [
      {
        Sid    = "InvokeEmbeddingEndpoint"
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint"
        ]
        Resource = "arn:aws:sagemaker:${var.aws_region}:${data.aws_caller_identity.current.account_id}:endpoint/${var.embedding_endpoint_name}"
      },
      {
        Sid    = "QueryS3Vectors"
        Effect = "Allow"
        Action = [
          "s3vectors:QueryVectors",
          "s3vectors:GetVectors"
        ]
        Resource = "*"
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
    ] : [],
    var.openai_api_key_ssm_parameter_name != "" ? [
      {
        Sid    = "ReadOpenAIKeyFromSSM"
        Effect = "Allow"
        Action = [
          "ssm:GetParameter"
        ]
        Resource = "arn:aws:ssm:${var.aws_region}:${data.aws_caller_identity.current.account_id}:parameter/${trimprefix(var.openai_api_key_ssm_parameter_name, "/")}"
      }
    ] : []
  )

  package_files = [
    "${path.root}/../../agents/FrontierAgent/lambda_handler.py",
    "${path.root}/../../agents/FrontierAgent/frontier_agent.py",
    "${path.root}/../../agents/FrontierAgent/requirements.lambda.txt",
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

resource "aws_iam_role_policy" "frontier_runtime_policy" {
  name = "${var.project_name}-runtime-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version   = "2012-10-17"
    Statement = local.frontier_runtime_policy_statements
  })
}

resource "terraform_data" "package_frontier_lambda" {
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

resource "aws_lambda_function" "frontier_agent" {
  function_name    = var.lambda_function_name
  role             = aws_iam_role.lambda_execution_role.arn
  runtime          = "python3.12"
  handler          = "src.agents.FrontierAgent.lambda_handler.lambda_handler"
  filename         = local.deployment_package_path
  source_code_hash = terraform_data.package_frontier_lambda.output
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  architectures    = ["x86_64"]

  environment {
    variables = local.frontier_environment
  }

  depends_on = [
    terraform_data.package_frontier_lambda,
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy.frontier_runtime_policy,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "frontier_agent" {
  name              = "/aws/lambda/${aws_lambda_function.frontier_agent.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}
