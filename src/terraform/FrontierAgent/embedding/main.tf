terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.70"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.13"
    }
  }

  # Using local backend - state will be stored in terraform.tfstate in this directory
  # This is automatically gitignored for security
}

provider "aws" {
  region = var.aws_region
}

data "aws_caller_identity" "current" {}

locals {
  image_context_dir = abspath("${path.module}/../../../agents/EmbeddingEndpoint")
  image_dockerfile  = "${local.image_context_dir}/Dockerfile"
  image_source_files = [
    for rel_path in fileset(local.image_context_dir, "**") :
    rel_path
    if !startswith(rel_path, "__pycache__/")
  ]
  sagemaker_environment = merge(
    {
      EMBEDDING_MODEL_ID   = var.embedding_model_name
      EMBEDDING_BATCH_SIZE = tostring(var.embedding_batch_size)
      NORMALIZE_EMBEDDINGS = tostring(var.normalize_embeddings)
      MODEL_DEVICE         = "cpu"
    },
    var.huggingface_api_token != "" ? {
      HF_TOKEN = var.huggingface_api_token
    } : {}
  )
}

resource "aws_s3_bucket" "product_data" {
  bucket        = var.product_data_bucket_name
  force_destroy = var.product_data_bucket_force_destroy

  tags = var.tags
}

resource "aws_s3_bucket_versioning" "product_data" {
  bucket = aws_s3_bucket.product_data.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "product_data" {
  bucket = aws_s3_bucket.product_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "product_data" {
  bucket = aws_s3_bucket.product_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_ecr_repository" "embedding" {
  name                 = "${var.project_name}-repo"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = var.tags
}

resource "terraform_data" "build_embedding_image" {
  count = var.auto_build_image ? 1 : 0

  input = base64sha256(join("", concat(
    [
      aws_ecr_repository.embedding.repository_url,
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
      aws_ecr_repository.embedding.repository_url,
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
      cmd /c "${var.aws_cli_executable} ecr get-login-password --region ${var.aws_region} | ${var.docker_executable} login --username AWS --password-stdin ${split("/", aws_ecr_repository.embedding.repository_url)[0]}"
      ${var.docker_executable} buildx build --platform ${var.docker_platform} --provenance=false --push -f "${local.image_dockerfile}" -t "${aws_ecr_repository.embedding.repository_url}:${var.image_tag}" "${local.image_context_dir}"
    EOT
    interpreter = ["PowerShell", "-Command"]
  }

  depends_on = [aws_ecr_repository.embedding]
}

resource "aws_iam_role" "sagemaker_role" {
  name = "${var.project_name}-sagemaker-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "sagemaker.amazonaws.com"
        }
      }
    ]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "sagemaker_execution_policy" {
  name = "${var.project_name}-sagemaker-execution-policy"
  role = aws_iam_role.sagemaker_role.id

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

resource "aws_sagemaker_model" "embedding_model" {
  name               = "${var.project_name}-model"
  execution_role_arn = aws_iam_role.sagemaker_role.arn

  primary_container {
    image       = "${aws_ecr_repository.embedding.repository_url}:${var.image_tag}"
    environment = local.sagemaker_environment
  }

  depends_on = [
    terraform_data.build_embedding_image,
    aws_iam_role_policy.sagemaker_execution_policy,
  ]

  tags = var.tags
}

resource "aws_sagemaker_endpoint_configuration" "serverless_config" {
  name = "${var.project_name}-serverless-config"

  production_variants {
    variant_name           = "AllTraffic"
    model_name             = aws_sagemaker_model.embedding_model.name
    initial_variant_weight = 1.0

    serverless_config {
      memory_size_in_mb = var.endpoint_memory_size_in_mb
      max_concurrency   = var.endpoint_max_concurrency
    }
  }

  tags = var.tags
}

resource "time_sleep" "wait_for_iam_propagation" {
  depends_on = [
    aws_iam_role_policy.sagemaker_execution_policy,
  ]

  create_duration = "15s"
}

resource "aws_sagemaker_endpoint" "embedding_endpoint" {
  for_each             = toset(var.embedding_endpoint_names)
  name                 = each.value
  endpoint_config_name = aws_sagemaker_endpoint_configuration.serverless_config.name

  depends_on = [
    time_sleep.wait_for_iam_propagation,
  ]

  tags = var.tags
}
