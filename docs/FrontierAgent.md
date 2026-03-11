# Building FlipFinder: Frontier Agent Lambda Deployment

Welcome back! In this guide, we'll deploy the Frontier Agent as an AWS Lambda pricing service. This agent uses retrieval-augmented generation: it embeds the incoming description with a SageMaker embedding endpoint, queries S3 Vectors for similar products, and asks an OpenAI model to estimate a price.

## Architecture Overview

## Why Lambda?

We're using Lambda for the Frontier Agent for several important reasons:
1. **The core logic is orchestration around APIs**: it coordinates embeddings, vector search, and an LLM call instead of hosting a model directly
2. **It scales well for bursty workloads**: pricing requests can arrive irregularly, and Lambda handles that cleanly
3. **It is cheaper than another dedicated endpoint**: the expensive model hosting is isolated to the embedding endpoint

## What We're Building

We'll deploy:
- A zip-packaged Python Lambda for the Frontier Agent
- An IAM execution role with permission to invoke the embedding endpoint and query S3 Vectors
- Optional IAM access to OpenAI credentials from Secrets Manager or SSM Parameter Store
- A CloudWatch log group for Frontier Agent logs
- Infrastructure as Code using Terraform

The key difference from the Specialist Agent approach: this deployment does **not** host a pricing model in SageMaker. It relies on:
- the embedding endpoint in `src/terraform/FrontierAgent/embedding`
- an S3 Vectors index populated with product vectors
- an OpenAI API key for the frontier model call

## Prerequisites

Before starting:
- Complete your AWS permissions setup for Lambda, SageMaker invoke, S3 Vectors, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Python available locally for Terraform packaging
- Have AWS CLI configured and authenticated
- Deploy the embedding endpoint first using [EmbeddingEndpoint.md](EmbeddingEndpoint.md)
- Make sure your S3 Vectors bucket and index already contain product vectors
- Have an OpenAI API key available through one of these methods:
  - direct Terraform variable
  - AWS Secrets Manager secret ARN
  - SSM SecureString parameter name

## Step 1: Configure Terraform Variables

First, set up the Terraform configuration for this guide:

```bash
# Navigate to the Frontier Agent terraform directory
cd src/terraform/FrontierAgent

# Copy the example variables file
copy terraform.tfvars.example terraform.tfvars
```

On PowerShell, you can also use:

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set your values:

```hcl
aws_region           = "us-east-1"
project_name         = "frontier-agent"
lambda_function_name = "frontier-agent-pricer"

openai_api_key                    = ""
openai_api_key_secret_arn         = ""
openai_api_key_ssm_parameter_name = ""

frontier_model          = "gpt-5.1"
frontier_aws_region     = "us-east-1"
frontier_vector_bucket  = "products-vectors-194722416872"
frontier_index_name     = "products"
embedding_endpoint_name = "flipfinder-embedding-endpoint"
frontier_top_k          = 5

python_executable = "python"
```

Important notes:
- Set **one** OpenAI credential source if possible
- The Lambda first checks `OPENAI_API_KEY`, then Secrets Manager, then SSM
- `embedding_endpoint_name` must match the SageMaker endpoint created by the embedding stack
- `frontier_vector_bucket` and `frontier_index_name` must point to an existing populated S3 Vectors index
- `image_tag` is **not** used by this module, even if it appears in older local files

## Step 2: Choose How to Provide the OpenAI API Key

You have three supported options.

### Option A: Put the key directly in `terraform.tfvars`

```hcl
openai_api_key = "sk-..."
```

This is the simplest setup, but it stores the key in Terraform-managed config.

### Option B: Use AWS Secrets Manager

Set:

```hcl
openai_api_key         = ""
openai_api_key_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:openai-key"
```

The secret can contain:
- a raw API key string
- or JSON with one of these keys:
  - `OPENAI_API_KEY`
  - `openai_api_key`
  - `api_key`

### Option C: Use SSM Parameter Store

Set:

```hcl
openai_api_key                    = ""
openai_api_key_ssm_parameter_name = "/openai/api_key"
```

The parameter should be a `SecureString`.

## Step 3: Deploy the Frontier Agent

This module packages the Lambda zip automatically during `terraform apply`.

```bash
# Initialize Terraform
terraform init

# Deploy the Frontier Agent
terraform apply
```

When prompted, type `yes` to confirm the deployment.

This will:
- Install the Lambda dependencies listed in `src/agents/FrontierAgent/requirements.lambda.txt`
- Build `src/terraform/FrontierAgent/lambda/frontier_agent.zip`
- Create the Lambda execution role and runtime policy
- Create the Frontier Agent Lambda function
- Create the CloudWatch log group

## Step 4: Understanding What Was Created

Terraform created several resources:

1. **Lambda Execution Role**: allows the agent to write logs and call dependent AWS services
2. **Runtime Policy**: grants `sagemaker:InvokeEndpoint`, `s3vectors:QueryVectors`, `s3vectors:GetVectors`, and optional secret read permissions
3. **Deployment Package**: a zip bundle built locally by `package.py`
4. **Frontier Lambda Function**: the inference entrypoint
5. **CloudWatch Log Group**: stores request latency and failure logs

The runtime environment includes:
- `DEFAULT_AWS_REGION`
- `FRONTIER_AWS_REGION`
- `FRONTIER_VECTOR_BUCKET`
- `FRONTIER_INDEX_NAME`
- `FRONTIER_SAGEMAKER_ENDPOINT`
- `FRONTIER_TOP_K`
- `FRONTIER_MODEL`
- optionally `OPENAI_API_KEY`
- optionally `OPENAI_API_KEY_SECRET_ARN`
- optionally `OPENAI_API_KEY_SSM_PARAMETER_NAME`

### Save Your Configuration

If your local app or scripts will call the Frontier Agent directly, update your `.env` file with the deployed values:

```text
DEFAULT_AWS_REGION=us-east-1
FRONTIER_AWS_REGION=us-east-1
FRONTIER_LAMBDA_NAME=frontier-agent-pricer
FRONTIER_SAGEMAKER_ENDPOINT=flipfinder-embedding-endpoint
FRONTIER_VECTOR_BUCKET=products-vectors-194722416872
FRONTIER_INDEX_NAME=products
FRONTIER_TOP_K=5
```

Terraform outputs are shown at the end of `terraform apply`. You can also view them anytime with:

```bash
terraform output
```

## Step 5: Test the Frontier Agent

Let's verify the Frontier Agent works with a simple test.

On Mac or Linux:

```bash
aws lambda invoke \
  --function-name frontier-agent-pricer \
  --payload '{"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  response.json

cat response.json
```

On Windows:

```powershell
aws lambda invoke --function-name "frontier-agent-pricer" --payload "{\"description\":\"Apple iPhone 13 Pro 256GB unlocked smartphone\"}" response.json

Get-Content response.json
```

You should see a Lambda proxy-style response whose `body` contains:
- `price`

If the agent succeeds but the price looks unreasonable, the root cause is usually one of these:
- the embedding endpoint is returning bad vectors
- the S3 Vectors index is empty or mismatched
- the OpenAI model is not the one you intended to use

## Cost Analysis

Your Frontier Agent cost comes from three places:
- **Lambda**: per invocation and duration
- **SageMaker embedding endpoint**: the embedding call happens on every request
- **OpenAI API**: each request also makes a chat completion call

The Lambda itself is usually not the main cost driver. The embedding endpoint and OpenAI usage matter more.

## Troubleshooting

If the Frontier Agent invocation fails:

1. **Check the Frontier Lambda logs**:
```bash
aws logs tail /aws/lambda/frontier-agent-pricer --follow
```

2. **Verify the runtime configuration**:
```bash
aws lambda get-function-configuration --function-name frontier-agent-pricer
```

You should see environment variables including `FRONTIER_SAGEMAKER_ENDPOINT`, `FRONTIER_VECTOR_BUCKET`, `FRONTIER_INDEX_NAME`, `FRONTIER_TOP_K`, and `FRONTIER_MODEL`.

3. **Verify the embedding endpoint exists**:
```bash
aws sagemaker describe-endpoint --endpoint-name flipfinder-embedding-endpoint
```

Status should be `InService`.

4. **Check the embedding endpoint directly**:
```bash
aws sagemaker-runtime invoke-endpoint \
  --endpoint-name flipfinder-embedding-endpoint \
  --content-type application/json \
  --body '{"inputs":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  /dev/stdout
```

5. **Verify the S3 Vectors index name and bucket**:
Make sure the configured bucket and index exist and contain vectors produced by the current embedding pipeline.

### Missing OpenAI API Key

If the Lambda fails with a message like:

```text
Missing OpenAI API key. Set OPENAI_API_KEY, OPENAI_API_KEY_SECRET_ARN, or OPENAI_API_KEY_SSM_PARAMETER_NAME.
```

the root cause is that none of the supported credential sources were available in the runtime environment.

### Secrets Manager or SSM Access Denied

If you configured a secret ARN or parameter name and the Lambda still fails, confirm:
- the Terraform variables were set correctly
- the Lambda IAM policy includes the matching secret or parameter permission
- the secret or parameter exists in the same AWS account and region you expect

### SageMaker Invoke Failure

If embedding generation fails, confirm:
- the endpoint name in `embedding_endpoint_name` is correct
- the Lambda region matches the region where the endpoint was deployed
- the embedding endpoint is healthy and returning pooled sentence embeddings

### Empty or Poor Retrieval Results

If prices are poor or inconsistent, the likely root cause is retrieval quality. Check:
- whether your S3 Vectors index is populated
- whether the vectors were generated from the same embedding model currently serving the endpoint
- whether metadata includes both `text` and `price`

### Terraform Packaging Fails

If `terraform apply` fails during packaging, check:
- that `python_executable` points to a working Python install
- that `pip` can install `openai` and `python-dotenv`
- that Windows can download compatible wheels for Python 3.12 when packaging

## Understanding Frontier vs Specialist

We chose this Frontier design because:
- **It uses retrieval for context**: similar items from S3 Vectors help the LLM ground its estimate
- **It stays flexible**: you can change the frontier model without rebuilding a container
- **It is lightweight to deploy**: the inference logic fits cleanly into Lambda

We did **not** use SageMaker for the pricing step here because the frontier layer is calling a hosted LLM API, not running a custom model locally.

## Operations in AWS

### What to Monitor

For this agent, the important operational signals are:
- **Lambda duration**
- **Lambda error count**
- **Embedding endpoint latency**
- **OpenAI failure rate**
- **Retrieval quality issues**, usually visible through logs and bad price outputs

### Explore in the AWS Console

Navigate to these sections:

1. **AWS Lambda Console**:
   ```
   https://console.aws.amazon.com/lambda/
   ```

2. **Check Your Function**:
   - Open `frontier-agent-pricer`
   - Review configuration, environment variables, and CloudWatch metrics

3. **Check CloudWatch Logs**:
   - Open the log group for the Frontier Agent
   - Review `frontier_lambda_success`, `frontier_lambda_failure`, and `frontier_price_success`

4. **Check the Embedding Endpoint**:
   - Open SageMaker
   - Inspect `flipfinder-embedding-endpoint`
   - Review endpoint health and invocation metrics

### Try This: Check Frontier Lambda Metrics

While your agent is running, check CloudWatch metrics:

```bash
aws cloudwatch get-metric-statistics --namespace "AWS/Lambda" --metric-name "Invocations" --dimensions Name=FunctionName,Value=frontier-agent-pricer --start-time 2026-03-10T00:00:00Z --end-time 2026-03-10T23:59:59Z --period 300 --statistics Sum --region us-east-1
```

This shows how often your Frontier Agent is being called.

## Clean Up (Optional)

If you need to tear down just the Frontier Agent infrastructure:

```bash
cd src/terraform/FrontierAgent
terraform destroy
```

This removes the Lambda function, IAM role, and CloudWatch log group. It does **not** remove the embedding endpoint or the S3 Vectors data.

## Next Steps

Your Frontier Agent is ready to serve retrieval-augmented price estimates.

Next useful steps are:
1. Validate the embedding endpoint outputs before trusting retrieval quality
2. Re-ingest vectors if you changed the embedding model
3. Move the OpenAI API key to Secrets Manager or SSM if it is still inline
4. Wire the Frontier Lambda into the Ensemble Agent or the full `src/terraform/Platform` stack
