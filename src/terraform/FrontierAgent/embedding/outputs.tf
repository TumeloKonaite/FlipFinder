output "ecr_repository_url" {
  description = "Terraform-managed ECR repository for the custom embedding image"
  value       = aws_ecr_repository.embedding.repository_url
}

output "sagemaker_endpoint_name" {
  description = "Primary SageMaker embedding endpoint name"
  value       = var.embedding_endpoint_names[0]
}

output "sagemaker_endpoint_names" {
  description = "Names of all SageMaker embedding endpoints"
  value       = sort([for endpoint in aws_sagemaker_endpoint.embedding_endpoint : endpoint.name])
}

output "product_data_bucket_name" {
  description = "S3 bucket name for raw product ingestion data"
  value       = aws_s3_bucket.product_data.bucket
}

output "product_data_bucket_arn" {
  description = "ARN of the S3 bucket for raw product ingestion data"
  value       = aws_s3_bucket.product_data.arn
}

output "sagemaker_endpoint_arn" {
  description = "ARN of the primary SageMaker endpoint"
  value       = aws_sagemaker_endpoint.embedding_endpoint[var.embedding_endpoint_names[0]].arn
}

output "sagemaker_endpoint_arns" {
  description = "ARNs of all SageMaker embedding endpoints"
  value       = { for name, endpoint in aws_sagemaker_endpoint.embedding_endpoint : name => endpoint.arn }
}

output "setup_instructions" {
  description = "Instructions for building and deploying the custom embedding service"
  value       = <<-EOT
    One-command deployment:
    1. terraform init
    2. terraform apply

    Local prerequisites:
    - Docker with buildx available as ${var.docker_executable}
    - AWS CLI available as ${var.aws_cli_executable}

    Auto-build enabled: ${var.auto_build_image}
    Image: ${aws_ecr_repository.embedding.repository_url}:${var.image_tag}

    After deployment:
    - Primary endpoint: ${var.embedding_endpoint_names[0]}
    - All endpoints: ${join(", ", var.embedding_endpoint_names)}
    - Recreate or clean the vector index before ingesting new sentence embeddings.
  EOT
}
