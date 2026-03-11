# Building FlipFinder: Ensemble Agent Orchestrator Deployment

Welcome back! In this guide, we'll deploy the Ensemble Agent as an AWS Lambda orchestrator. This is the layer that rewrites the product description, calls the Frontier, Specialist, and NN pricing agents in parallel, and combines their responses into a single predicted dollar value.

## Architecture Overview

## Why Lambda?

We're using Lambda for the Ensemble Agent for several important reasons:
1. **It is an orchestrator, not a model host**: this layer coordinates other agents instead of serving a model directly
2. **Parallel fan-out**: it invokes the Frontier, Specialist, and NN agents concurrently and combines successful responses
3. **Lower operational overhead**: a zip-packaged Lambda is simpler and cheaper than standing up another always-on endpoint

## What We're Building

We'll deploy:
- A zip-packaged Python Lambda for the Ensemble Agent
- An IAM execution role with permission to invoke the three downstream pricing Lambdas
- A CloudWatch log group for orchestration logs
- An optional public Lambda Function URL
- Infrastructure as Code using Terraform

The key difference from the Specialist Agent approach: this deployment does **not** create another SageMaker endpoint. The Specialist Agent still uses SageMaker, but the Ensemble Agent only orchestrates downstream services.

## Prerequisites

Before starting:
- Complete your AWS permissions setup for Lambda, Bedrock, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Python available locally for Terraform packaging
- Have AWS CLI configured and authenticated
- Deploy these agents first:
  - `src/terraform/FrontierAgent`
  - `src/terraform/SpecialistAgent`
  - `src/terraform/NNAgent`
- Have Bedrock access to the preprocessor model you plan to use

## Step 1: Configure Terraform Variables

First, set up the Terraform configuration for this guide:

```bash
# Navigate to the Ensemble Agent terraform directory
cd src/terraform/EnsembleAgent

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
project_name         = "ensemble-agent"
lambda_function_name = "ensemble-agent-orchestrator"

frontier_lambda_name   = "frontier-agent-pricer"
frontier_lambda_arn    = "arn:aws:lambda:us-east-1:123456789012:function:frontier-agent-pricer"
specialist_lambda_name = "pricer-service-wrapper"
specialist_lambda_arn  = "arn:aws:lambda:us-east-1:123456789012:function:pricer-service-wrapper"
nn_lambda_name         = "nn-agent-pricer"
nn_lambda_arn          = "arn:aws:lambda:us-east-1:123456789012:function:nn-agent-pricer"

preprocessor_model         = "bedrock/converse/openai.gpt-oss-120b-1:0"
ensemble_weight_frontier   = 0.8
ensemble_weight_specialist = 0.1
ensemble_weight_nn         = 0.1

create_function_url = false
python_executable   = "python"
```

Important notes:
- This module requires **both** the downstream Lambda names and ARNs
- The Lambda names are used at runtime; the ARNs are used for the IAM invoke policy
- `create_function_url` is optional and defaults to `false`
- `image_tag` is **not** used by this module, even if it appears in older local files

## Step 2: Collect the Downstream Lambda Names and ARNs

If you deployed the agents individually, get their outputs now.

From `src/terraform/FrontierAgent`:

```bash
terraform output -raw lambda_function_name
terraform output -raw lambda_function_arn
```

From `src/terraform/SpecialistAgent`:

```bash
terraform output -raw lambda_function_name
terraform output -raw lambda_function_arn
```

From `src/terraform/NNAgent`:

```bash
terraform output -raw lambda_function_name
terraform output -raw lambda_function_arn
```

Then paste those values into `src/terraform/EnsembleAgent/terraform.tfvars`.

If you are deploying from `src/terraform/Platform`, that higher-level stack wires these values automatically and you may not need the standalone Ensemble Agent module.

## Step 3: Deploy the Ensemble Agent

This module packages the Lambda zip automatically during `terraform apply`.

```bash
# Initialize Terraform
terraform init

# Deploy the Ensemble Agent
terraform apply
```

When prompted, type `yes` to confirm the deployment.

This will:
- Install the Lambda dependencies listed in `src/agents/EnsembleAgent/requirements.lambda.txt`
- Build `src/terraform/EnsembleAgent/lambda/ensemble_agent.zip`
- Create the Lambda execution role and runtime policy
- Create the Ensemble Agent Lambda function
- Create the CloudWatch log group
- Optionally create a Function URL if enabled

## Step 4: Understanding What Was Created

Terraform created several resources:

1. **Lambda Execution Role**: allows the orchestrator to write logs and invoke the Frontier, Specialist, and NN Lambdas
2. **Lambda Runtime Policy**: grants `lambda:InvokeFunction` to the three downstream agents and Bedrock invoke permissions for preprocessing
3. **Deployment Package**: a zip bundle built locally by `package.py`
4. **Ensemble Lambda Function**: the orchestrator entrypoint
5. **CloudWatch Log Group**: stores preprocessing, downstream invocation, and aggregation logs
6. **Optional Function URL**: created only if `create_function_url = true`

The runtime environment includes:
- `DEFAULT_AWS_REGION`
- `BEDROCK_AWS_REGION`
- `PRICER_PREPROCESSOR_MODEL`
- `FRONTIER_AGENT_LAMBDA_NAME`
- `SPECIALIST_AGENT_LAMBDA_NAME`
- `NN_AGENT_LAMBDA_NAME`
- `ENSEMBLE_REQUIRE_REMOTE_AGENTS=true`
- the three ensemble weights

### Save Your Configuration

If your local app or scripts will call the Ensemble Agent directly, update your `.env` file with the deployed name:

```text
DEFAULT_AWS_REGION=us-east-1
ENSEMBLE_LAMBDA_NAME=ensemble-agent-orchestrator
```

If you enabled a Function URL, you may also want:

```text
ENSEMBLE_FUNCTION_URL=https://<generated-id>.lambda-url.us-east-1.on.aws/
```

Terraform outputs are shown at the end of `terraform apply`. You can also view them anytime with:

```bash
terraform output
```

## Step 5: Test the Orchestrator

Let's verify the Ensemble Agent works with a simple test.

On Mac or Linux:

```bash
aws lambda invoke \
  --function-name ensemble-agent-orchestrator \
  --payload '{"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  response.json

cat response.json
```

On Windows:

```powershell
aws lambda invoke --function-name "ensemble-agent-orchestrator" --payload "{\"description\":\"Apple iPhone 13 Pro 256GB unlocked smartphone\"}" response.json

Get-Content response.json
```

You should see a Lambda proxy-style response whose `body` contains:
- `price`
- `rewrite`
- `preprocessor_latency_ms`
- `latency_ms`
- `components`
- `weights`

If you enabled a Function URL, you can also test it directly:

```bash
curl -X POST "<FUNCTION_URL>" \
  -H "Content-Type: application/json" \
  -d '{"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"}'
```

**Note**: total latency depends on Bedrock preprocessing plus the slowest downstream agent, especially the Specialist Agent if its SageMaker endpoint is cold.

## Cost Analysis

Your Ensemble Agent:
- **Does not run continuously**: you pay per Lambda invocation and duration
- **Calls Bedrock**: preprocessing cost depends on the model and token usage
- **Calls other agents**: overall cost still includes the Frontier, Specialist, and NN services
- **Inherits Specialist endpoint cost**: the most expensive component remains the Specialist SageMaker endpoint

## Troubleshooting

If the orchestrator invocation fails:

1. **Check the Ensemble Lambda logs**:
```bash
aws logs tail /aws/lambda/ensemble-agent-orchestrator --follow
```

2. **Verify the runtime configuration**:
```bash
aws lambda get-function-configuration --function-name ensemble-agent-orchestrator
```

You should see environment variables including `PRICER_PREPROCESSOR_MODEL`, `FRONTIER_AGENT_LAMBDA_NAME`, `SPECIALIST_AGENT_LAMBDA_NAME`, `NN_AGENT_LAMBDA_NAME`, and the ensemble weights.

3. **Check the downstream agent logs**:
```bash
aws logs tail /aws/lambda/<frontier-lambda-name> --follow
aws logs tail /aws/lambda/<specialist-lambda-name> --follow
aws logs tail /aws/lambda/<nn-lambda-name> --follow
```

4. **Verify Bedrock access in the correct region**:
```bash
aws bedrock list-foundation-models --region us-east-1
```

**Note**: if you're not in the default region, add `--region your-region` to these commands.

### Packaging Fails With a Missing `preprocessor.py`

If `terraform apply` fails while building the deployment zip and the error mentions `src/agents/preprocessor.py`, the root cause is in `src/terraform/EnsembleAgent/package.py`. That script currently copies `src/agents/preprocessor.py`, but the real file in this repo is `src/agents/EnsembleAgent/preprocessor.py`.

### Runtime Error About Missing Lambda Targets

If you see an error about required remote agents, the root cause is that this module sets:

```text
ENSEMBLE_REQUIRE_REMOTE_AGENTS=true
```

That means all three downstream Lambda names must be present in the deployed environment.

### Bedrock Access Denied

If preprocessing fails with an access error, confirm:
- your AWS identity can invoke the selected Bedrock model
- the model is available in `BEDROCK_AWS_REGION`
- `preprocessor_model` uses a valid Bedrock model ID format

### Timeout Errors

If the Ensemble Agent times out:
- increase `lambda_timeout`
- check whether the Specialist SageMaker endpoint is cold or unhealthy
- check whether a downstream Lambda is timing out before returning

### Function URL Missing

If `terraform output lambda_function_url` returns `null`, that is expected when:

```hcl
create_function_url = false
```

## Understanding Orchestration vs a Single Endpoint

We chose Lambda orchestration because:
- **The Ensemble Agent is coordination logic**: it does not host a model
- **The downstream services already exist**: Frontier, Specialist, and NN each handle their own inference path
- **Parallel execution fits Lambda well**: the code uses a thread pool and renormalizes weights across successful results

We did **not** choose another SageMaker endpoint because this layer does not need GPU hosting or a custom model container.

## Operations in AWS

### What to Monitor

For this orchestrator, the important operational signals are:
- **Invocation count**: how often the ensemble is used
- **Duration**: total latency including preprocessing and downstream fan-out
- **Error count**: failures in preprocessing or downstream Lambda invocations
- **Component health**: whether one agent is failing often enough to skew the weighted average

### Explore in the AWS Console

Navigate to these sections:

1. **AWS Lambda Console**:
   ```
   https://console.aws.amazon.com/lambda/
   ```

2. **Check Your Function**:
   - Open `ensemble-agent-orchestrator`
   - Review configuration, environment variables, and CloudWatch metrics
   - If enabled, verify the Function URL

3. **Check CloudWatch Logs**:
   - Open the log group for the Ensemble Agent
   - Review `preprocessor_complete`, `agent_success`, `agent_failure`, and `ensemble_complete` events

4. **Inspect Downstream Functions**:
   - Open the Frontier, Specialist, and NN Lambdas
   - Confirm their names match the values configured in the ensemble environment

### Try This: Check Lambda Metrics

While your orchestrator is running, check CloudWatch metrics:

```bash
aws cloudwatch get-metric-statistics --namespace "AWS/Lambda" --metric-name "Invocations" --dimensions Name=FunctionName,Value=ensemble-agent-orchestrator --start-time 2026-03-10T00:00:00Z --end-time 2026-03-10T23:59:59Z --period 300 --statistics Sum --region us-east-1
```

This shows how often your orchestrator is being called.

## Clean Up (Optional)

If you need to tear down just the Ensemble Agent infrastructure:

```bash
cd src/terraform/EnsembleAgent
terraform destroy
```

This removes the Lambda function, IAM role, CloudWatch log group, and optional Function URL.

## Next Steps

Your Ensemble Agent is ready to orchestrate the pricing stack.

Next useful steps are:
1. Add CloudWatch alarms for Lambda errors and duration
2. Wire the Ensemble Agent into your application flow
3. Add retries or fallbacks for specific downstream agent failures
4. Consider deploying from `src/terraform/Platform` if you want the full stack wired together automatically
