# Embedding Endpoint

This stack deploys a custom SageMaker serverless endpoint that returns one pooled sentence embedding per input. It replaces the stock `HF_TASK=feature-extraction` setup that emitted token-level tensors and caused oversized payloads during ingestion.

## What Changed

- Custom Docker image managed through Terraform-backed ECR
- `SentenceTransformer` inference service with `/ping` and `/invocations`
- Optional multiple identical SageMaker endpoints from one Terraform stack
- Environment-driven model name, normalization, and internal batch size

## Deploy

From `src/terraform/FrontierAgent/embedding`:

```bash
terraform init
terraform apply -target=aws_ecr_repository.embedding
terraform output -raw ecr_repository_url
```

Build and push the image:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com
docker buildx build --platform linux/amd64 --provenance=false --push -t <ECR_REPOSITORY_URL>:latest ../../agents/EmbeddingEndpoint
```

Then complete the deployment:

```bash
terraform apply
```

## Invoke

Single input:

```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name flipfinder-embedding-endpoint \
  --content-type application/json \
  --body '{"inputs":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  /dev/stdout
```

Batch input:

```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name flipfinder-embedding-endpoint \
  --content-type application/json \
  --body '{"inputs":["Apple iPhone 13 Pro","Samsung Galaxy S24"]}' \
  /dev/stdout
```

The response is one sentence embedding per input, shaped to remain compatible with the existing ingestion and query clients.

## Important

Do not mix vectors produced by the old token-level endpoint with vectors from this endpoint in the same index. Recreate or clean the S3 Vectors index before re-ingesting.
