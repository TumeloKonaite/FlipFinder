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
  image_context_dir = abspath("${path.module}/../../agents/NNAgent")
  image_dockerfile  = "${local.image_context_dir}/Dockerfile.lambda"
  image_source_files = [
    for rel_path in fileset(local.image_context_dir, "**") :
    rel_path
    if !startswith(rel_path, "__pycache__/")
  ]
}

resource "aws_ecr_repository" "nn_agent" {
  name                 = "${var.project_name}-repo"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "terraform_data" "build_nn_image" {
  count = var.auto_build_image ? 1 : 0

  input = base64sha256(join("", concat(
    [
      aws_ecr_repository.nn_agent.repository_url,
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
      aws_ecr_repository.nn_agent.repository_url,
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
      cmd /c "${var.aws_cli_executable} ecr get-login-password --region ${var.aws_region} | ${var.docker_executable} login --username AWS --password-stdin ${split("/", aws_ecr_repository.nn_agent.repository_url)[0]}"
      ${var.docker_executable} buildx build --platform ${var.docker_platform} --provenance=false --push -f "${local.image_dockerfile}" -t "${aws_ecr_repository.nn_agent.repository_url}:${var.image_tag}" "${local.image_context_dir}"
    EOT
    interpreter = ["PowerShell", "-Command"]
  }

  depends_on = [aws_ecr_repository.nn_agent]
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

resource "aws_lambda_function" "nn_agent" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_execution_role.arn
  package_type  = "Image"
  image_uri     = "${aws_ecr_repository.nn_agent.repository_url}:${var.image_tag}"
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size
  architectures = ["x86_64"]

  image_config {
    command = ["lambda_handler.lambda_handler"]
  }

  environment {
    variables = {
      DEFAULT_AWS_REGION = var.aws_region
    }
  }

  depends_on = [
    terraform_data.build_nn_image,
    aws_iam_role_policy_attachment.lambda_basic_execution,
  ]

  tags = var.tags
}

resource "aws_cloudwatch_log_group" "nn_agent" {
  name              = "/aws/lambda/${aws_lambda_function.nn_agent.function_name}"
  retention_in_days = var.log_retention_in_days
  tags              = var.tags
}
