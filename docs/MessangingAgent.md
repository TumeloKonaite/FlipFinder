# Building FlipFinder: Messaging Agent Notification Setup

Welcome back! In this guide, we'll configure the Messaging Agent that sends deal alerts for FlipFinder. In the current repo, the Messaging Agent is not deployed as a standalone Lambda. It is packaged inside the `PlanningAgent` deployment, where it drafts deal notifications with Bedrock and sends them through Amazon SNS email.

## Architecture Overview

## Why SNS + Bedrock?

We're using SNS plus Bedrock for the Messaging Agent for several important reasons:
1. **SNS handles delivery cleanly**: AWS manages the email topic and subscription flow
2. **Bedrock writes the message text**: the agent can generate concise deal summaries instead of sending raw data only
3. **It fits the planner workflow**: notifications are a side effect of `PlanningAgent`, not a separate inference service

## What We're Building

We'll configure:
- An SNS topic for deal alerts
- An optional email subscription endpoint
- Bedrock-backed message drafting inside the Planning Agent runtime
- IAM permissions for SNS publish and Bedrock model invocation
- Infrastructure as Code through the `PlanningAgent` Terraform module

The key difference from the other agent guides: there is **no standalone MessagingAgent Terraform stack** in this repo. The messaging behavior is deployed as part of `src/terraform/PlanningAgent`.

## Prerequisites

Before starting:
- Complete your AWS permissions setup for Lambda, SNS, Bedrock, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Python available locally for Terraform packaging
- Have AWS CLI configured and authenticated
- Deploy or know the Lambda names and ARNs for:
  - `ScannerAgent`
  - `EnsembleAgent`
- Have Bedrock model access for the messaging model you plan to use
- Have an email address available if you want SNS email delivery

## Step 1: Configure PlanningAgent Variables

Because MessagingAgent is packaged into PlanningAgent, configure it there:

```bash
# Navigate to the Planning Agent terraform directory
cd src/terraform/PlanningAgent

# Copy the example variables file
copy terraform.tfvars.example terraform.tfvars
```

On PowerShell, you can also use:

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
- `messaging_email_endpoint` is optional, but without it SNS has nowhere to deliver email
- `messaging_bedrock_model_id` defaults to `amazon.nova-micro-v1:0`
- the Messaging Agent subject line is built automatically from the product description and discount
- notifications are only sent when `PlanningAgent` finds a discount above its threshold

## Step 2: Understand How Messaging Is Wired

The `PlanningAgent` Terraform module does the messaging setup automatically:
- creates the SNS topic
- optionally creates the SNS email subscription
- passes `MESSAGING_SNS_TOPIC_ARN` into the PlanningAgent Lambda environment
- passes `MESSAGING_BEDROCK_REGION` and `MESSAGING_BEDROCK_MODEL_ID`
- grants `sns:Publish` and Bedrock invoke permissions

This means you do **not** deploy MessagingAgent separately.

## Step 3: Deploy the PlanningAgent Stack

This module packages the PlanningAgent Lambda zip automatically during `terraform apply`.

```bash
# Initialize Terraform
terraform init

# Deploy PlanningAgent, including MessagingAgent integration
terraform apply
```

When prompted, type `yes` to confirm the deployment.

This will create:
- the PlanningAgent Lambda
- the SNS topic for deal alerts
- the optional email subscription
- the IAM role and runtime policy
- the CloudWatch log group

## Step 4: Confirm the SNS Email Subscription

If you set `messaging_email_endpoint`, AWS SNS sends a confirmation email to that address.

You must open that email and confirm the subscription. Until you do that, notifications will not be delivered even if the Lambda publishes successfully.

This is a common source of confusion and is the normal SNS behavior.

## Step 5: Understanding What Was Created

Terraform created several messaging-related resources:

1. **SNS Topic**: receives deal alert publish requests
2. **Optional SNS Email Subscription**: routes alerts to your inbox after confirmation
3. **PlanningAgent Lambda Runtime Environment**: includes the messaging settings
4. **IAM Policy**: allows SNS publish and Bedrock invocation
5. **CloudWatch Logs**: stores planner and messaging runtime logs

The relevant runtime environment variables are:
- `MESSAGING_SNS_TOPIC_ARN`
- `MESSAGING_BEDROCK_REGION`
- `MESSAGING_BEDROCK_MODEL_ID`

Terraform outputs include:
- the PlanningAgent Lambda name
- the PlanningAgent Lambda ARN
- the SNS topic ARN

### Save Your Configuration

If your local app or scripts will trigger the planning flow directly, update your `.env` file with the relevant values:

```text
DEFAULT_AWS_REGION=us-east-1
PLANNING_AGENT_LAMBDA_NAME=planning-agent-orchestrator
MESSAGING_BEDROCK_REGION=us-east-1
MESSAGING_BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
```

You can view the Terraform outputs anytime with:

```bash
terraform output
```

## Step 6: Test the Messaging Flow

The Messaging Agent is exercised through `PlanningAgent`, not directly.

First, trigger a planner run that can produce an alert:

```bash
aws lambda invoke --function-name planning-agent-orchestrator --payload "{}" response.json
```

Then inspect the result:

On Mac or Linux:

```bash
cat response.json
```

On Windows:

```powershell
Get-Content response.json
```

If a sufficiently good deal is found, PlanningAgent will:
1. call the ScannerAgent
2. call the EnsembleAgent
3. use MessagingAgent to publish an SNS email notification

If you want to validate delivery, also check your inbox for the confirmed email endpoint.

## Cost Analysis

Your messaging setup costs come from three places:
- **Lambda**: the PlanningAgent invocation
- **Bedrock**: message drafting tokens
- **SNS**: notification delivery

In most cases, this is much cheaper than running another dedicated model endpoint.

## Troubleshooting

If notifications are not arriving:

1. **Check the PlanningAgent logs**:
```bash
aws logs tail /aws/lambda/planning-agent-orchestrator --follow
```

2. **Verify the runtime configuration**:
```bash
aws lambda get-function-configuration --function-name planning-agent-orchestrator
```

You should see `MESSAGING_SNS_TOPIC_ARN`, `MESSAGING_BEDROCK_REGION`, and `MESSAGING_BEDROCK_MODEL_ID`.

3. **Check the SNS topic and subscriptions**:
```bash
aws sns list-subscriptions-by-topic --topic-arn <MESSAGING_SNS_TOPIC_ARN>
```

4. **Verify Bedrock access in the correct region**:
```bash
aws bedrock list-foundation-models --region us-east-1
```

### Email Subscription Never Delivers

If the planner logs show successful SNS publish but you never receive the email, the most likely root cause is that the SNS subscription was never confirmed from the inbox confirmation email.

### MESSAGING_SNS_TOPIC_ARN Missing

If the runtime errors mention `MESSAGING_SNS_TOPIC_ARN`, the root cause is that the Messaging Agent only works inside the deployed PlanningAgent environment where Terraform injects that SNS topic ARN.

### Bedrock Access Denied

If message drafting fails with Bedrock access errors, confirm:
- your AWS identity can invoke the selected model
- the model exists in `messaging_bedrock_region`
- the PlanningAgent IAM policy was deployed successfully

### No Alerts Even Though the System Runs

If everything appears healthy but you get no emails, the likely root cause is workflow logic, not delivery:
- `PlanningAgent` only notifies when the best discount exceeds its threshold
- if no strong deal is found, messaging is skipped by design

## Understanding MessagingAgent vs Standalone Notification Services

We chose this design because:
- **Messaging is part of the planner workflow**: it is an output step, not an independent service
- **SNS simplifies delivery**: no custom SMTP or email infrastructure is needed
- **Bedrock keeps messages readable**: alerts can be concise and useful instead of raw JSON

We did **not** create a standalone MessagingAgent Lambda because the current repo packages this logic directly into the PlanningAgent Lambda.

## Operations in AWS

### What to Monitor

For messaging, the important operational signals are:
- **Planner invocation count**
- **Planner errors**
- **SNS publish success**
- **Email subscription status**
- **Bedrock message generation failures**

### Explore in the AWS Console

Navigate to these sections:

1. **AWS Lambda Console**:
   ```
   https://console.aws.amazon.com/lambda/
   ```

2. **Check PlanningAgent**:
   - Open `planning-agent-orchestrator`
   - Review environment variables and CloudWatch metrics

3. **Check SNS**:
   - Open the SNS topic created for deal alerts
   - Confirm the email subscription status is `Confirmed`

4. **Check CloudWatch Logs**:
   - Review the PlanningAgent logs for scanner, ensemble, and messaging activity

## SNS + Bedrock vs Building Your Own Notification Stack

| Aspect | SNS + Bedrock | Custom Notification Service |
|--------|----------------|-----------------------------|
| **Delivery** | Managed by AWS SNS | You manage infrastructure |
| **Message Writing** | Bedrock-generated | Usually handwritten templates |
| **Operational Overhead** | Lower | Higher |
| **Best For** | Integrated agent workflows | Highly customized notification platforms |

### Try This: Check SNS Topic Details

After deployment, inspect the topic:

```bash
aws sns get-topic-attributes --topic-arn <MESSAGING_SNS_TOPIC_ARN>
```

This confirms the messaging topic exists and is available for publish operations.

## Clean Up (Optional)

If you need to tear down the messaging setup, destroy the PlanningAgent stack:

```bash
cd src/terraform/PlanningAgent
terraform destroy
```

This removes the PlanningAgent Lambda, SNS topic, email subscription, IAM role, and related resources created by that stack.

## Next Steps

Your Messaging Agent setup is ready inside the planner workflow.

Next useful steps are:
1. Confirm the SNS email subscription immediately after deployment
2. Trigger a planner run with known-good deals to validate end-to-end delivery
3. Tune the Bedrock model or prompt if the email wording is not good enough
4. Add CloudWatch alarms for planner failures or SNS delivery issues
