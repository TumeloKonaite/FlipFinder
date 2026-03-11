# Building FlipFinder: Planning Agent Orchestrator Deployment

In this guide, you'll deploy the Planning Agent as an AWS Lambda orchestrator. This is the workflow layer that pulls candidate deals from the Scanner Agent, prices them with the Ensemble Agent, calculates the discount, and sends an alert through the Messaging Agent when the best opportunity clears the planner threshold.

## Architecture Overview

## Why Lambda?

We're using Lambda for the Planning Agent for three practical reasons:
1. **It is orchestration logic**: the planner coordinates other agents instead of serving a model itself
2. **It fits event-driven execution**: you can invoke it manually, from an app flow, or from future scheduled workflows
3. **It keeps the system modular**: Scanner, Ensemble, and Messaging stay independently deployable and easier to debug

## What We're Building

We'll deploy:
- A zip-packaged Python Lambda for the Planning Agent
- An IAM execution role that can invoke the Scanner and Ensemble Lambdas
- An SNS topic for deal alerts
- An optional SNS email subscription
- Bedrock-backed messaging configuration for alert text generation
- A CloudWatch log group for planner logs
- Infrastructure as Code with Terraform

This stack does **not** create a SageMaker endpoint. The Planning Agent is coordination logic that sits on top of already-deployed services.

## Prerequisites

Before starting:
- Have AWS permissions for Lambda, SNS, Bedrock, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Python available locally for Terraform packaging
- Have AWS CLI configured and authenticated
- Deploy these stacks first:
  - `src/terraform/ScannerAgent`
  - `src/terraform/EnsembleAgent`
- Have Bedrock access to the messaging model you want to use
- Have an email address ready if you want SNS email delivery

## Step 1: Configure Terraform Variables

Set up the Terraform configuration for this guide:

```bash
cd src/terraform/PlanningAgent
copy terraform.tfvars.example terraform.tfvars
```

On PowerShell, this also works:

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` and set your values:

```hcl
aws_region                = "us-east-1"
project_name              = "planning-agent"
lambda_function_name      = "planning-agent-orchestrator"
lambda_timeout            = 180
lambda_memory_size        = 1024

scanner_lambda_name       = "scanner-agent-runner"
scanner_lambda_arn        = "arn:aws:lambda:us-east-1:123456789012:function:scanner-agent-runner"
ensemble_lambda_name      = "pricing-ensemble-orchestrator"
ensemble_lambda_arn       = "arn:aws:lambda:us-east-1:123456789012:function:pricing-ensemble-orchestrator"

messaging_sns_topic_name   = "deal-alerts"
messaging_email_endpoint   = "you@example.com"
messaging_bedrock_region   = "us-east-1"
messaging_bedrock_model_id = "amazon.nova-micro-v1:0"

python_executable = "python"
```

Important notes:
- This module requires both downstream Lambda names and ARNs
- The names are used at runtime; the ARNs are used in the IAM invoke policy
- `messaging_email_endpoint` is optional, but without it SNS email delivery will not happen
- `messaging_bedrock_model_id` defaults to `amazon.nova-micro-v1:0`

## Step 2: Collect the Downstream Lambda Names and ARNs

If you deployed the agents separately, fetch their outputs now.

From `src/terraform/ScannerAgent`:

```bash
terraform output -raw lambda_function_name
terraform output -raw lambda_function_arn
```

From `src/terraform/EnsembleAgent`:

```bash
terraform output -raw lambda_function_name
terraform output -raw lambda_function_arn
```

Paste those values into `src/terraform/PlanningAgent/terraform.tfvars`.

If you're using `src/terraform/Platform`, that higher-level stack can wire these values automatically.

## Step 3: Deploy the Planning Agent

This module packages the Lambda zip automatically during `terraform apply`.

```bash
terraform init
terraform apply
```

When prompted, type `yes`.

This creates:
- the Planning Agent Lambda
- the SNS topic
- the optional SNS email subscription
- the IAM execution role and runtime policy
- the CloudWatch log group

## Step 4: Confirm the SNS Email Subscription

If you set `messaging_email_endpoint`, AWS SNS sends a confirmation email to that address.

You must confirm the subscription from that email. Until you do, the planner can publish successfully and you still will not receive notifications.

## Step 5: Understanding What Was Created

Terraform creates:

1. **Planning Lambda Function**: orchestrates scanning, pricing, and alerting
2. **Runtime Policy**: allows `lambda:InvokeFunction`, `sns:Publish`, and Bedrock model invocation
3. **SNS Topic**: receives deal alert publish requests
4. **Optional Email Subscription**: routes alerts to your inbox after confirmation
5. **CloudWatch Log Group**: stores planner success and failure logs
6. **Deployment Package**: the zip built locally by `package.py`

Runtime environment variables include:
- `DEFAULT_AWS_REGION`
- `SCANNER_AGENT_LAMBDA_NAME`
- `ENSEMBLE_AGENT_LAMBDA_NAME`
- `MESSAGING_SNS_TOPIC_ARN`
- `MESSAGING_BEDROCK_REGION`
- `MESSAGING_BEDROCK_MODEL_ID`

Important outputs include:
- `lambda_function_name`
- `lambda_function_arn`
- `messaging_sns_topic_arn`

### Save Your Configuration

If local scripts or application code will invoke the planner directly, update `.env` with:

```text
DEFAULT_AWS_REGION=us-east-1
PLANNING_AGENT_LAMBDA_NAME=planning-agent-orchestrator
SCANNER_AGENT_LAMBDA_NAME=scanner-agent-runner
ENSEMBLE_AGENT_LAMBDA_NAME=pricing-ensemble-orchestrator
MESSAGING_BEDROCK_REGION=us-east-1
MESSAGING_BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
```

You can view outputs anytime with:

```bash
terraform output
```

## Step 6: Test the Planning Agent

Run a basic invocation:

On Mac or Linux:

```bash
aws lambda invoke \
  --function-name planning-agent-orchestrator \
  --payload '{}' \
  response.json

cat response.json
```

On Windows:

```powershell
aws lambda invoke --function-name "planning-agent-orchestrator" --payload "{}" response.json
Get-Content response.json
```

You should receive a Lambda proxy-style response whose `body` contains:
- `opportunity`
- `notified`

If the best deal exceeds the threshold, `notified` will be `true` and the Messaging Agent will publish to SNS.

You can also provide prior memory explicitly:

```json
{"memory":["https://example.com/deal-1","https://example.com/deal-2"]}
```

## Cost Analysis

The Planning Agent itself is usually not the main cost driver. Total cost comes from:
- **Lambda** for planner execution
- **Scanner Agent** and its OpenAI usage
- **Ensemble Agent** and its downstream pricing calls
- **Bedrock** for alert drafting
- **SNS** for notification delivery

## Troubleshooting

If planner invocation fails:

1. **Check the planner logs**
```bash
aws logs tail /aws/lambda/planning-agent-orchestrator --follow
```

2. **Check deployed configuration**
```bash
aws lambda get-function-configuration --function-name planning-agent-orchestrator
```

You should see `SCANNER_AGENT_LAMBDA_NAME`, `ENSEMBLE_AGENT_LAMBDA_NAME`, `MESSAGING_SNS_TOPIC_ARN`, `MESSAGING_BEDROCK_REGION`, and `MESSAGING_BEDROCK_MODEL_ID`.

3. **Check SNS subscriptions**
```bash
aws sns list-subscriptions-by-topic --topic-arn <MESSAGING_SNS_TOPIC_ARN>
```

4. **Check downstream logs**
```bash
aws logs tail /aws/lambda/<scanner-lambda-name> --follow
aws logs tail /aws/lambda/<ensemble-lambda-name> --follow
```

### Missing Downstream Lambda Targets

If the planner fails while invoking Scanner or Ensemble, confirm:
- the Lambda names in `terraform.tfvars` are correct
- the ARNs match the same deployed functions
- the downstream Lambdas exist in the expected account and region

### SNS Notifications Not Arriving

If `notified` is `true` but no email arrives, the most likely root cause is an unconfirmed SNS email subscription.

### Bedrock Access Denied

If alert drafting fails with Bedrock access errors, confirm:
- your AWS identity can invoke the selected model
- the model exists in `MESSAGING_BEDROCK_REGION`
- the planner IAM policy deployed successfully

### No Opportunity Returned

If the planner returns:

```json
{"opportunity": null, "notified": false}
```

the likely cause is workflow logic rather than infrastructure:
- Scanner found no suitable deals
- Ensemble priced the deals but none cleared the threshold
- the best discount was below `PlanningAgent.DEAL_THRESHOLD`

## Understanding the Planning Layer

We chose this design because:
- **It coordinates the whole deal workflow** in one place
- **It composes separate agents cleanly** without merging them into a monolith
- **It centralizes decision logic** such as best-deal selection and notification thresholding

We did **not** use SageMaker here because the planner is orchestration code, not model hosting.

## Operations in AWS

### What to Monitor

Key operational signals:
- **Invocation count**
- **Duration**
- **Error count**
- **Notification rate**
- **Scanner and Ensemble health**
- **SNS subscription status**

### Explore in the AWS Console

Navigate to:

1. **AWS Lambda**
   - Open `planning-agent-orchestrator`
   - Review configuration, environment variables, and CloudWatch metrics

2. **CloudWatch Logs**
   - Review `planning_lambda_success` and `planning_lambda_failure`

3. **SNS**
   - Open the deal alerts topic
   - Confirm the email subscription is `Confirmed`

4. **Downstream Lambdas**
   - Open the Scanner and Ensemble functions
   - Confirm their names match the planner environment

## Lambda Orchestration vs a Single Monolith

| Aspect | Orchestrated Lambdas | Single Combined Service |
|--------|----------------------|-------------------------|
| **Modularity** | Higher | Lower |
| **Independent Deployment** | Easier | Harder |
| **Operational Isolation** | Better | Worse |
| **Best For** | Agent-based workflows | Small tightly-coupled systems |

### Try This: Check Lambda Metrics

```bash
aws cloudwatch get-metric-statistics --namespace "AWS/Lambda" --metric-name "Invocations" --dimensions Name=FunctionName,Value=planning-agent-orchestrator --start-time 2026-03-10T00:00:00Z --end-time 2026-03-10T23:59:59Z --period 300 --statistics Sum --region us-east-1
```

## Clean Up (Optional)

To remove just the Planning Agent stack:

```bash
cd src/terraform/PlanningAgent
terraform destroy
```

This removes the PlanningAgent Lambda, SNS topic, optional email subscription, IAM role, and related resources created by that stack.

## Next Steps

Your Planning Agent is ready to coordinate FlipFinder's deal workflow.

Next useful steps:
1. Confirm the SNS email subscription immediately after deployment
2. Trigger a planner run and verify both downstream invocations succeed
3. Adjust the planner discount threshold in code if alerts are too frequent or too rare
4. Deploy `src/terraform/Platform` if you want the full stack wired together automatically
