# Building FlipFinder: Scanner Agent Scheduled Lambda Deployment

In this guide, we'll deploy the Scanner Agent as a scheduled AWS Lambda. This is the component that reads deals from RSS feeds, filters out items already seen in memory, asks OpenAI to select the most promising products with clear prices, and stores scanned results in DynamoDB for future runs.

## Architecture Overview

## Why Lambda + EventBridge + DynamoDB?

We're using this combination for several important reasons:
1. **Lambda runs the scanner on demand or on a schedule**: ideal for periodic RSS polling
2. **EventBridge triggers repeated scans automatically**: no separate scheduler service is needed
3. **DynamoDB stores scanner memory**: previously seen deal URLs can be skipped in later runs

## What We're Building

We'll deploy:
- A zip-packaged Python Lambda for the Scanner Agent
- A DynamoDB table that stores scanned deal URLs and summary data
- An EventBridge rule that triggers the scanner on a fixed schedule
- An IAM execution role with DynamoDB and optional Secrets Manager access
- A CloudWatch log group for scanner logs
- Infrastructure as Code using Terraform

The key difference from the Specialist Agent approach: this deployment does **not** use SageMaker or container images. It is a scheduled Lambda workflow with OpenAI plus AWS primitives.

## Prerequisites

Before starting:
- Complete your AWS permissions setup for Lambda, EventBridge, DynamoDB, Secrets Manager, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Python available locally for Terraform packaging
- Have AWS CLI configured and authenticated
- Have an OpenAI API key available either directly or through Secrets Manager

## Step 1: Configure Terraform Variables

First, set up the Terraform configuration for this guide:

```bash
# Navigate to the Scanner Agent terraform directory
cd src/terraform/ScannerAgent

# Copy the example variables file
copy terraform.tfvars.example terraform.tfvars
```

On PowerShell, you can also use:

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set your values:

```hcl
aws_region                  = "us-east-1"
project_name                = "scanner-agent"
lambda_function_name        = "scanner-agent-runner"
lambda_timeout              = 180
lambda_memory_size          = 1024
lambda_reserved_concurrency = null

scanner_schedule_expression = "rate(30 minutes)"
scanner_memory_table_name   = "scanner-agent-memory"
scanner_memory_max_items    = 500

openai_api_key_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:scanner-agent/openai-api-key"
openai_api_key            = ""

python_executable = "python"
```

Important notes:
- Prefer `openai_api_key_secret_arn` over an inline `openai_api_key`
- `scanner_schedule_expression` controls how often EventBridge triggers the Lambda
- `scanner_memory_max_items` limits how many remembered URLs are loaded from DynamoDB each run
- `lambda_reserved_concurrency` should usually stay `null` unless you need to pin scanner concurrency

## Step 2: Choose How to Provide the OpenAI API Key

You have two supported options.

### Option A: Use Secrets Manager

Set:

```hcl
openai_api_key_secret_arn = "arn:aws:secretsmanager:us-east-1:123456789012:secret:scanner-agent/openai-api-key"
openai_api_key            = ""
```

The secret can contain:
- a raw API key string
- or JSON with one of these keys:
  - `OPENAI_API_KEY`
  - `openai_api_key`
  - `api_key`

### Option B: Pass the key directly

Set:

```hcl
openai_api_key = "sk-..."
```

This is simpler, but stores the key in Terraform-managed config.

## Step 3: Deploy the Scanner Agent

This module packages the Lambda zip automatically during `terraform apply`.

```bash
# Initialize Terraform
terraform init

# Deploy the Scanner Agent
terraform apply
```

When prompted, type `yes` to confirm the deployment.

This will create:
- the Scanner Agent Lambda
- the DynamoDB memory table
- the EventBridge schedule rule and target
- the IAM execution role and runtime policy
- the CloudWatch log group

## Step 4: Understanding What Was Created

Terraform created several resources:

1. **Scanner Lambda Function**: runs RSS scraping and LLM-based deal selection
2. **DynamoDB Memory Table**: stores previously scanned deal URLs and metadata
3. **EventBridge Rule**: invokes the scanner on the configured schedule
4. **EventBridge Target and Lambda Permission**: allow the scheduled trigger to call the Lambda
5. **IAM Runtime Policy**: grants DynamoDB access and optional Secrets Manager read access
6. **CloudWatch Log Group**: stores invocation and failure logs

The runtime environment includes:
- `DEFAULT_AWS_REGION`
- `SCANNER_MEMORY_TABLE`
- `SCANNER_MEMORY_MAX_ITEMS`
- optionally `OPENAI_API_KEY_SECRET_ARN`
- optionally `OPENAI_API_KEY`

### Save Your Configuration

If your local app or scripts will invoke the Scanner Agent directly, update your `.env` file with the deployed values:

```text
DEFAULT_AWS_REGION=us-east-1
SCANNER_AGENT_LAMBDA_NAME=scanner-agent-runner
SCANNER_MEMORY_TABLE=scanner-agent-memory
SCANNER_MEMORY_MAX_ITEMS=500
```

Terraform outputs are shown at the end of `terraform apply`. You can also view them anytime with:

```bash
terraform output
```

## Step 5: Test the Scanner Agent

Let's verify the Scanner Agent works with a simple manual invocation.

On Mac or Linux:

```bash
aws lambda invoke \
  --function-name scanner-agent-runner \
  --payload "{}" \
  response.json

cat response.json
```

On Windows:

```powershell
aws lambda invoke --function-name "scanner-agent-runner" --payload "{}" response.json

Get-Content response.json
```

You should see a Lambda proxy-style response whose `body` contains:
- `message`
- `deals_found`
- `deals`

If the scanner found new candidates, the selected deals will also be written into DynamoDB memory.

## Step 6: Understand the Schedule

The Scanner Agent is also triggered automatically by EventBridge using the configured expression, for example:

```text
rate(30 minutes)
```

You can inspect the rule name with:

```bash
terraform output scanner_schedule_rule_name
```

That scheduled trigger is separate from manual Lambda invocation. Both paths use the same runtime logic.

## Cost Analysis

Your Scanner Agent cost comes from four places:
- **Lambda**: per invocation and duration
- **OpenAI API**: each scan calls the model to select the best deals
- **DynamoDB**: PAY_PER_REQUEST usage for scanner memory reads and writes
- **CloudWatch Logs**: minor logging cost

This is generally much cheaper than always-on model hosting.

## Troubleshooting

If the scanner invocation fails:

1. **Check the Lambda logs**:
```bash
aws logs tail /aws/lambda/scanner-agent-runner --follow
```

2. **Verify the runtime configuration**:
```bash
aws lambda get-function-configuration --function-name scanner-agent-runner
```

You should see `SCANNER_MEMORY_TABLE`, `SCANNER_MEMORY_MAX_ITEMS`, and one OpenAI credential source.

3. **Check the DynamoDB table exists**:
```bash
aws dynamodb describe-table --table-name scanner-agent-memory
```

4. **Check the EventBridge rule exists**:
```bash
aws events describe-rule --name scanner-agent-schedule
```

If you changed `project_name`, the rule name will also change.

### Missing OpenAI API Key

If the Lambda fails with a message like:

```text
Missing OpenAI API key. Set OPENAI_API_KEY or OPENAI_API_KEY_SECRET_ARN.
```

the root cause is that neither supported credential source was available in the runtime environment.

### Secrets Manager Access Denied

If you configured `openai_api_key_secret_arn` and the Lambda still fails, confirm:
- the secret ARN is correct
- the secret exists in the expected region
- the ScannerAgent IAM policy includes `secretsmanager:GetSecretValue`

### DynamoDB Errors

If memory loading or persistence fails, confirm:
- the table name in `SCANNER_MEMORY_TABLE` is correct
- the Lambda role has DynamoDB permissions
- the table exists in the same AWS region as the Lambda

### No Deals Found

If the run succeeds but returns `deals_found = 0`, the likely root cause is not infrastructure:
- the RSS feeds may not have new items
- the memory table may already contain recent URLs
- the LLM may have rejected ambiguous or poorly priced deals

### Schedule Not Triggering

If manual invocation works but automatic scans never run, check:
- the EventBridge rule was created
- the Lambda permission for `events.amazonaws.com` exists
- the schedule expression is valid

## Understanding Scanner vs Ensemble

We chose this Scanner design because:
- **It is a discovery layer**: it finds candidate deals before pricing happens
- **It benefits from scheduled execution**: RSS feeds should be checked repeatedly
- **It needs memory**: DynamoDB prevents the same deals from being surfaced again and again

We did **not** use SageMaker here because the scanner is an orchestration and extraction workflow, not a hosted model endpoint.

## Operations in AWS

### What to Monitor

For this agent, the important operational signals are:
- **Invocation count**
- **Duration**
- **Error count**
- **DynamoDB read/write activity**
- **EventBridge trigger health**
- **OpenAI failures or low-quality deal selection**

### Explore in the AWS Console

Navigate to these sections:

1. **AWS Lambda Console**:
   ```
   https://console.aws.amazon.com/lambda/
   ```

2. **Check Your Function**:
   - Open `scanner-agent-runner`
   - Review configuration, environment variables, and CloudWatch metrics

3. **Check DynamoDB**:
   - Open the scanner memory table
   - Inspect stored URLs and selected deal records

4. **Check EventBridge**:
   - Open the rule for the scanner schedule
   - Confirm the Lambda target is attached

5. **Check CloudWatch Logs**:
   - Review `scanner_lambda_success` and `scanner_lambda_failure`

## Lambda + DynamoDB vs Custom Cron Infrastructure

| Aspect | Lambda + DynamoDB + EventBridge | Custom Cron Service |
|--------|---------------------------------|---------------------|
| **Scheduling** | Managed by EventBridge | You manage it |
| **Memory Store** | DynamoDB | Custom database or files |
| **Operational Overhead** | Lower | Higher |
| **Best For** | Periodic deal discovery workflows | Highly customized schedulers |

### Try This: Check Lambda Metrics

While your scanner is running, check CloudWatch metrics:

```bash
aws cloudwatch get-metric-statistics --namespace "AWS/Lambda" --metric-name "Invocations" --dimensions Name=FunctionName,Value=scanner-agent-runner --start-time 2026-03-10T00:00:00Z --end-time 2026-03-10T23:59:59Z --period 300 --statistics Sum --region us-east-1
```

This shows how often your Scanner Agent is being called.

## Clean Up (Optional)

If you need to tear down just the Scanner Agent infrastructure:

```bash
cd src/terraform/ScannerAgent
terraform destroy
```

This removes the Lambda function, DynamoDB table, EventBridge schedule, IAM role, and related Terraform-managed resources.

## Next Steps

Your Scanner Agent is ready to discover and shortlist candidate deals.

Next useful steps are:
1. Verify the EventBridge schedule is actually firing after deployment
2. Inspect the DynamoDB memory table after a few runs
3. Move the OpenAI API key to Secrets Manager if it is still inline
4. Wire the ScannerAgent into the `PlanningAgent` or full `Platform` stack if you want end-to-end automation
