# Building FlipFinder: Part 2 - Specialist Agent SageMaker Deployment

Welcome back! In this guide, we'll deploy the Specialist Agent as a custom SageMaker real-time endpoint backed by a Hugging Face base model plus a PEFT adapter. This is a critical component - it powers FlipFinder's pricing specialist and returns a predicted dollar value for a product description.

## Architecture Overview

## Why SageMaker?

We're using SageMaker for several important reasons:
1. **Production-ready**: Handles endpoint hosting, health checks, monitoring, and availability
2. **GPU support**: Needed for our custom LLM inference container using quantization and PEFT
3. **Professional skill**: SageMaker is widely used in industry AI deployments

## What We're Building

We'll deploy:
- A custom Docker inference container for the Specialist Agent
- An ECR repository managed by Terraform
- A SageMaker real-time endpoint on GPU
- A lightweight Lambda wrapper that calls `InvokeEndpoint`
- Infrastructure as Code using Terraform

The key difference from the embedding endpoint approach: this deployment uses a custom container because we need to load a base model, attach a LoRA/PEFT adapter, and run custom prompt and price parsing logic.

## Prerequisites

Before starting:
- Complete [1_permissions.md](1_permissions.md)
- Have Terraform installed (version 1.5+)
- Have Docker Desktop installed and running
- Have AWS CLI configured and authenticated
- Have access to the Hugging Face model and adapter repos

## Step 1: Configure Terraform Variables

First, let's set up the Terraform configuration for this guide:

```bash
# Navigate to the Specialist Agent terraform directory
cd src/terraform/SpecialistAgent

# Copy the example variables file
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set your values:

```hcl
aws_region = "us-east-1"

project_name            = "pricer-service"
image_tag               = "latest"
sagemaker_endpoint_name = "pricer-endpoint"
lambda_function_name    = "pricer-service-wrapper"

instance_type          = "ml.g5.xlarge"
initial_instance_count = 1

base_model      = "Qwen/Qwen2.5-3B-Instruct"
finetuned_model = "TumeloKonaite/<your-price-model-repo>"
model_revision  = ""

huggingface_api_token = ""

question       = "What does this cost to the nearest dollar?"
prefix         = "Price is $"
max_new_tokens = 5
seed           = 42
```

If either the base model or fine-tuned model repo is gated, set `huggingface_api_token` to your Hugging Face token.

If your Hugging Face repo is a PEFT adapter, keep `base_model` aligned with the model you trained against.
If you pushed a merged full model instead, the container now supports loading that repo directly and `model_revision` remains optional.

Important: if `terraform.tfvars` contains `huggingface_api_token = ""`, that value overrides
`TF_VAR_huggingface_api_token`. Either put the token in `terraform.tfvars`, remove that line and
use `TF_VAR_huggingface_api_token`, or pass `-var="huggingface_api_token=hf_..."` explicitly.

## Step 2: Create the ECR Repository with Terraform

Terraform manages the ECR repository for this deployment, but it does **not** build the Docker image. So the first safe step is creating the repository first:

```bash
# Initialize Terraform
terraform init

# Create only the ECR repository first
terraform apply -target=aws_ecr_repository.pricer
```

When prompted, type `yes` to confirm the deployment. This creates the repository where your custom Specialist Agent image will be pushed.

## Step 3: Build and Push the Specialist Agent Container

Now build the custom inference container and push it to the Terraform-managed ECR repo.

First, get the repository URL:

```bash
terraform output ecr_repository_url
```

Then log in to ECR, build the image, and push it.

On Mac or Linux:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 --provenance=false --push \
  -t <ECR_REPOSITORY_URL>:latest \
  ../../agents/SpecialistAgent
```

On Windows:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 --provenance=false --push -t <ECR_REPOSITORY_URL>:latest ../../agents/SpecialistAgent
```

**Important**: use `--platform linux/amd64 --provenance=false` when pushing to SageMaker. Without that, Docker may push an OCI manifest that SageMaker rejects.

## Step 4: Deploy the Full Stack

Now that the image exists in ECR, run a full apply:

```bash
terraform apply
```

When prompted, type `yes` to confirm the deployment. This will create:
- IAM role for SageMaker
- SageMaker model configuration pointing to your custom ECR image
- Real-time SageMaker endpoint
- Lambda wrapper function
- CloudWatch log group for Lambda

## Step 5: Understanding What Was Created

Terraform created several resources:

1. **ECR Repository**: Stores the custom Specialist Agent Docker image
2. **IAM Roles**: One for SageMaker, one for Lambda
3. **SageMaker Model**: Configuration pointing to the custom ECR image and runtime environment variables
4. **Real-Time Endpoint**: The GPU endpoint for Specialist Agent inference
5. **Lambda Wrapper**: A lightweight function that calls `InvokeEndpoint`

After deployment, Terraform will display important outputs including the ECR repository URL, endpoint name, and Lambda function name.

### Save Your Configuration

**Important**: Update your environment configuration with the endpoint name:

1. Note the endpoint name from Terraform output (should be `pricer-endpoint`)
2. Edit your `.env` file
3. Update these lines:
   ```
   DEFAULT_AWS_REGION=us-east-1
   SAGEMAKER_ENDPOINT_NAME=pricer-endpoint
   ```

You can also use the Lambda wrapper name from Terraform output if you want to invoke the wrapper directly:
```
PRICER_LAMBDA_NAME=pricer-service-wrapper
```

Tip: Terraform outputs are shown at the end of `terraform apply`. You can also view them anytime with:

```bash
terraform output
```

## Step 6: Test the Endpoint

Let's verify the endpoint works with a simple test.

On Mac or Linux:

```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name pricer-endpoint \
  --content-type application/json \
  --body '{"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  /dev/stdout
```

On Windows:

```bash
echo {"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"} > payload.json

aws sagemaker-runtime invoke-endpoint --endpoint-name "pricer-endpoint" --content-type "application/json" --body "fileb://payload.json" output.json

cat output.json
```

You should see a JSON object containing a predicted price and the raw generated text.

You can also test the Lambda wrapper:

```bash
aws lambda invoke --function-name pricer-service-wrapper --payload "{\"description\":\"Apple iPhone 13 Pro 256GB unlocked smartphone\"}" response.json
cat response.json
```

**Note**: The first request can be slow because the container must start and load the model.

## Cost Analysis

Your real-time endpoint:
- **Runs continuously**: You pay while the endpoint is provisioned
- **GPU-backed**: Higher cost than serverless embeddings, but needed for this model architecture
- **Primary cost driver**: The `ml.g5.xlarge` instance
- **Estimated cost**: Significantly higher than the embedding endpoint, so remember to destroy it when not needed

## Troubleshooting

If the endpoint invocation fails:

1. **Check endpoint status**:
```bash
aws sagemaker describe-endpoint --endpoint-name pricer-endpoint
```
Status should be `InService`

2. **Check endpoint logs**:
```bash
aws logs tail /aws/sagemaker/Endpoints/pricer-endpoint --follow
```

3. **Check the model environment**:
```bash
aws sagemaker describe-model --model-name pricer-service-model --query 'PrimaryContainer.Environment'
```

You should see environment variables including `BASE_MODEL`, `FINETUNED_MODEL`, `QUESTION`, `PREFIX`, `MAX_NEW_TOKENS`, and `SEED`.

4. **Verify the image exists in ECR**:
```bash
aws ecr describe-images --repository-name pricer-service-repo --region us-east-1
```

**Note**: If you're not in the default region, add `--region your-region` to these commands.

## Understanding Real-Time vs Serverless

We chose a real-time endpoint because:
- **GPU support**: Required for this inference setup
- **Custom container**: Needed to load a base model and attach a PEFT adapter
- **Lower latency after startup**: Better suited to repeated pricing requests

We did **not** choose serverless because this model setup uses custom GPU inference and does not fit the serverless limits or startup model.

## Troubleshooting

### Requested Image Not Found

If you see:

```text
Requested image ... not found
```

Terraform created the ECR repo, but SageMaker could not find the image tag yet. Push the image to ECR first, then rerun `terraform apply`.

### Unsupported Manifest Media Type

If SageMaker rejects the ECR image manifest, rebuild and push with:

```bash
docker buildx build --platform linux/amd64 --provenance=false --push -t <ECR_REPOSITORY_URL>:latest ../../agents/SpecialistAgent
```

### CannotStartContainerError

If the endpoint fails with:

```text
CannotStartContainerError
```

This usually means the container does not satisfy the SageMaker hosting contract. The container must respond to:
- `GET /ping`
- `POST /invocations`
- and start correctly when SageMaker runs `serve`

### Endpoint Already Exists Error

If you see "Cannot create already existing endpoint" during `terraform apply`, SageMaker may still be deleting the old endpoint. Wait a few minutes and check:

```bash
aws sagemaker describe-endpoint --endpoint-name pricer-endpoint --region us-east-1
```

When it no longer exists, rerun:

```bash
terraform apply
```

### Terraform Apply Takes Forever

Real-time GPU endpoints can take several minutes to create. Be patient and don't interrupt the process unless you have evidence it is stuck.

### Docker Not Running

If `docker build` or `docker push` fails with Docker engine errors, start Docker Desktop and verify:

```bash
docker version
docker info
```

## Clean Up (Optional)

If you need to tear down just the Specialist Agent infrastructure:

```bash
cd src/terraform/SpecialistAgent
terraform destroy
```

This will remove the SageMaker endpoint, Lambda wrapper, IAM roles, and other Terraform-managed resources. The ECR repository is protected with `prevent_destroy`, so you will need to remove that lifecycle rule first if you want Terraform to delete it too.

## Next Steps

Congratulations! You've deployed a production-grade custom model on AWS.

Next useful steps are:
1. Add autoscaling policies for the endpoint
2. Move the Hugging Face token into Secrets Manager
3. Add CloudWatch alarms and endpoint monitoring
4. Test the Lambda wrapper from the application path

Your Specialist Agent endpoint is ready and waiting.
