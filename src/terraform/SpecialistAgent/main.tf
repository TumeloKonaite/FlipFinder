terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.4"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

data "archive_file" "pricer_wrapper_zip" {
  type        = "zip"
  source_file = "${path.module}/${var.lambda_source_file}"
  output_path = "${path.module}/lambda/pricer_service.zip"
}

locals {
  image_context_dir = abspath("${path.module}/../../agents/SpecialistAgent")
  image_dockerfile  = "${local.image_context_dir}/Dockerfile"
  image_source_files = [
    for rel_path in fileset(local.image_context_dir, "**") :
    rel_path
    if !startswith(rel_path, "__pycache__/")
  ]
  sagemaker_environment = merge(
    {
      BASE_MODEL      = var.base_model
      FINETUNED_MODEL = var.finetuned_model
      MODEL_REVISION  = var.model_revision
      QUESTION        = var.question
      PREFIX          = var.prefix
      MAX_NEW_TOKENS  = tostring(var.max_new_tokens)
      SEED            = tostring(var.seed)
    },
    var.huggingface_api_token != "" ? {
      HF_TOKEN = var.huggingface_api_token
    } : {}
  )
}

resource "aws_ecr_repository" "pricer" {
  name                 = "${var.project_name}-repo"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "terraform_data" "build_pricer_image" {
  count = var.auto_build_image ? 1 : 0

  input = base64sha256(join("", concat(
    [
      aws_ecr_repository.pricer.repository_url,
      var.image_tag,
      var.docker_platform,
    ],
    [
      for rel_path in local.image_source_files :
      filemd5("${local.image_context_dir}/${rel_path}")
    ]
  )))

  triggers_replace = concat(
    [
      aws_ecr_repository.pricer.repository_url,
      var.image_tag,
      var.docker_platform,
    ],
    [
      for rel_path in local.image_source_files :
      filemd5("${local.image_context_dir}/${rel_path}")
    ]
  )

  provisioner "local-exec" {
    command     = <<-EOT
      $ErrorActionPreference = "Stop"
      cmd /c "${var.aws_cli_executable} ecr get-login-password --region ${var.aws_region} | ${var.docker_executable} login --username AWS --password-stdin ${split("/", aws_ecr_repository.pricer.repository_url)[0]}"
      ${var.docker_executable} buildx build --platform ${var.docker_platform} --provenance=false --push -f "${local.image_dockerfile}" -t "${aws_ecr_repository.pricer.repository_url}:${var.image_tag}" "${local.image_context_dir}"
    EOT
    interpreter = ["PowerShell", "-Command"]
  }

  depends_on = [aws_ecr_repository.pricer]
}

resource "aws_iam_role" "sagemaker_execution_role" {
  name = "${var.project_name}-sagemaker-execution-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "${var.project_name}-sagemaker-execution-policy"
  role = aws_iam_role.sagemaker_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EcrRead"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
          "ecr:BatchCheckLayerAvailability"
        ]
        Resource = "*"
      },
      {
        Sid    = "LogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_sagemaker_model" "pricer" {
  name               = "${var.project_name}-model"
  execution_role_arn = aws_iam_role.sagemaker_execution_role.arn

  primary_container {
    image       = "${aws_ecr_repository.pricer.repository_url}:${var.image_tag}"
    environment = local.sagemaker_environment
  }

  depends_on = [
    terraform_data.build_pricer_image,
    aws_iam_role_policy.sagemaker_execution_policy,
  ]

  tags = var.tags
}

resource "aws_sagemaker_endpoint_configuration" "pricer" {
  name = "${var.project_name}-endpoint-config"

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.pricer.name
    instance_type          = var.instance_type
    initial_instance_count = var.initial_instance_count
    initial_variant_weight = 1.0
  }

  tags = var.tags
}

resource "aws_sagemaker_endpoint" "pricer" {
  name                 = var.sagemaker_endpoint_name
  endpoint_config_name = aws_sagemaker_endpoint_configuration.pricer.name

  tags = var.tags
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

resource "aws_iam_role_policy" "lambda_execution_policy" {
  name = "${var.project_name}-lambda-execution-policy"
  role = aws_iam_role.lambda_execution_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "InvokeSageMaker"
        Effect = "Allow"
        Action = [
          "sagemaker:InvokeEndpoint"
        ]
        Resource = aws_sagemaker_endpoint.pricer.arn
      },
      {
        Sid    = "LogsWrite"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "*"
      }
    ]
  })
}

resource "aws_lambda_function" "pricer_wrapper" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_execution_role.arn
  handler       = "pricer_service.lambda_handler"
  runtime       = "python3.12"

  filename         = data.archive_file.pricer_wrapper_zip.output_path
  source_code_hash = data.archive_file.pricer_wrapper_zip.output_base64sha256

  timeout     = var.lambda_timeout
  memory_size = var.lambda_memory_size

  environment {
    variables = {
      SAGEMAKER_ENDPOINT_NAME = aws_sagemaker_endpoint.pricer.name
      DEFAULT_AWS_REGION      = var.aws_region
    }
  }

  depends_on = [
    aws_iam_role_policy.lambda_execution_policy,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "pricer_wrapper" {
  name              = "/aws/lambda/${aws_lambda_function.pricer_wrapper.function_name}"
  retention_in_days = 7
  tags              = var.tags
}
