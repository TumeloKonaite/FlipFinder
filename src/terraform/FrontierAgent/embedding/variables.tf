variable "aws_region" {
  description = "AWS region for resources"
  type        = string
}

variable "project_name" {
  description = "Prefix used for Terraform-managed embedding resources"
  type        = string
  default     = "embedding-service"
}

variable "product_data_bucket_name" {
  description = "Globally unique S3 bucket name for raw product ingestion data"
  type        = string
}

variable "product_data_bucket_force_destroy" {
  description = "Allow Terraform to delete the bucket even when it contains objects"
  type        = bool
  default     = false
}

variable "tags" {
  description = "Tags to apply to supported resources"
  type        = map(string)
  default     = {}
}

variable "image_tag" {
  description = "Docker image tag for the custom embedding container"
  type        = string
  default     = "latest"
}

variable "embedding_model_name" {
  description = "Name of the HuggingFace model to use"
  type        = string
  default     = "sentence-transformers/all-MiniLM-L6-v2"
}

variable "huggingface_api_token" {
  description = "Optional Hugging Face token for gated embedding models"
  type        = string
  sensitive   = true
  default     = ""
}

variable "normalize_embeddings" {
  description = "Whether the embedding service should L2-normalize output vectors"
  type        = bool
  default     = true
}

variable "embedding_batch_size" {
  description = "Internal batch size used by the SentenceTransformer container"
  type        = number
  default     = 32
}

variable "embedding_endpoint_names" {
  description = "Names of the SageMaker embedding endpoints to create"
  type        = list(string)
  default     = ["flipfinder-embedding-endpoint"]
}

variable "endpoint_memory_size_in_mb" {
  description = "Memory size for the SageMaker serverless embedding endpoint"
  type        = number
  default     = 3072
}

variable "endpoint_max_concurrency" {
  description = "Maximum concurrent invocations for the SageMaker serverless embedding endpoint"
  type        = number
  default     = 4
}

variable "docker_executable" {
  description = "Docker CLI executable used for building and pushing the embedding image"
  type        = string
  default     = "docker"
}

variable "aws_cli_executable" {
  description = "AWS CLI executable used for authenticating Docker against ECR"
  type        = string
  default     = "aws"
}

variable "docker_platform" {
  description = "Target platform for the embedding container image build"
  type        = string
  default     = "linux/amd64"
}

variable "auto_build_image" {
  description = "Whether Terraform should build and push the embedding image automatically"
  type        = bool
  default     = true
}
