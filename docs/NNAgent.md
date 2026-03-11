# Building FlipFinder: NN Agent Lambda Container Deployment

In this guide, we'll deploy the NN Agent as an AWS Lambda container image. This is the lightweight classical pricing component that loads a saved neural network model from the container image and returns a predicted dollar value for a product description.

## Architecture Overview

## Why Lambda Container Images?

We're using a Lambda container image for the NN Agent for several important reasons:
1. **The model and dependencies are packaged together**: PyTorch, scikit-learn, and the trained model binary ship in one image
2. **No separate model host is needed**: this agent performs in-process inference inside Lambda
3. **It keeps the deployment simple**: Terraform manages the ECR repository and Lambda, while Docker builds the image

## What We're Building

We'll deploy:
- An ECR repository managed by Terraform
- A Lambda container image for the NN Agent
- An IAM execution role for Lambda
- A CloudWatch log group for inference logs
- Infrastructure as Code using Terraform

The key difference from the Specialist Agent approach: this deployment does **not** use SageMaker. The NN weights are downloaded during Docker build and bundled into the Lambda image.

## Prerequisites

Before starting:
- Complete your AWS permissions setup for Lambda, ECR, IAM, and CloudWatch
- Have Terraform installed (version 1.5+)
- Have Docker Desktop installed and running
- Have AWS CLI configured and authenticated
- Have internet access to the NN weights folder:
  `https://drive.google.com/drive/folders/1uq5C9edPIZ1973dArZiEO-VE13F7m8MK?usp=drive_link`

## Step 1: Configure Terraform Variables

First, set up the Terraform configuration for this guide:

```bash
# Navigate to the NN Agent terraform directory
cd src/terraform/NNAgent

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
project_name         = "nn-agent"
lambda_function_name = "nn-agent-pricer"
image_tag            = "latest"

lambda_timeout     = 120
lambda_memory_size = 6144
nn_weights_drive_folder_url = "https://drive.google.com/drive/folders/1uq5C9edPIZ1973dArZiEO-VE13F7m8MK?usp=drive_link"

tags = {
  Project     = "nn-agent"
  Environment = "dev"
}
```

Important notes:
- `image_tag` is required by this module because the Lambda image URI is built from the ECR repo plus this tag
- `lambda_memory_size` is intentionally larger than the default in `variables.tf` in the checked-in example file
- The Docker image uses `public.ecr.aws/lambda/python:3.11` as its base image

## Step 2: Create the ECR Repository with Terraform

Terraform manages the ECR repository for this deployment, but it does **not** build the Docker image. Create the repository first:

```bash
# Initialize Terraform
terraform init

# Create only the ECR repository first
terraform apply -target=aws_ecr_repository.nn_agent
```

When prompted, type `yes` to confirm the deployment.

Then get the repository URL:

```bash
terraform output -raw ecr_repository_url
```

## Step 3: Build and Push the NN Agent Container

Now build the custom Lambda image and push it to the Terraform-managed ECR repo.

On Mac or Linux:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 --provenance=false --push \
  -f ../../agents/NNAgent/Dockerfile.lambda \
  -t <ECR_REPOSITORY_URL>:latest \
  ../../agents/NNAgent
```

On Windows:

```bash
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

docker buildx build --platform linux/amd64 --provenance=false --push -f ../../agents/NNAgent/Dockerfile.lambda -t <ECR_REPOSITORY_URL>:latest ../../agents/NNAgent
```

This image includes:
- `deep_neural_network.py`
- `inference_service.py`
- `lambda_handler.py`
- Python dependencies from `requirements.lambda.txt`
- NN weights downloaded from the Google Drive folder and copied into the image as `deep_neural_network_model.bin`

**Important**: use `--platform linux/amd64 --provenance=false` when pushing to Lambda. This avoids manifest issues and ensures the image matches the Lambda architecture configured by Terraform.

## Step 4: Deploy the Full Stack

Now that the image exists in ECR, run a full apply:

```bash
terraform apply
```

When prompted, type `yes` to confirm the deployment.

This will create:
- IAM role for Lambda
- Lambda function pointing at the ECR image
- CloudWatch log group for the NN Agent

## Step 5: Understanding What Was Created

Terraform created several resources:

1. **ECR Repository**: stores the NN Agent Lambda image
2. **Lambda Execution Role**: grants basic Lambda logging permissions
3. **Lambda Function**: runs the neural network model from the container image
4. **CloudWatch Log Group**: stores inference success and failure logs

At runtime, the Lambda loads the model lazily on first use from:

```text
deep_neural_network_model.bin
```

The function environment is intentionally minimal:
- `DEFAULT_AWS_REGION`

### Save Your Configuration

If your local app or scripts will call the NN Agent directly, update your `.env` file with the deployed name:

```text
DEFAULT_AWS_REGION=us-east-1
NN_AGENT_LAMBDA_NAME=nn-agent-pricer
```

Terraform outputs are shown at the end of `terraform apply`. You can also view them anytime with:

```bash
terraform output
```

## Step 6: Test the NN Agent

Let's verify the NN Agent works with a simple test.

On Mac or Linux:

```bash
aws lambda invoke \
  --function-name nn-agent-pricer \
  --payload '{"description":"Apple iPhone 13 Pro 256GB unlocked smartphone"}' \
  response.json

cat response.json
```

On Windows:

```powershell
aws lambda invoke --function-name "nn-agent-pricer" --payload "{\"description\":\"Apple iPhone 13 Pro 256GB unlocked smartphone\"}" response.json

Get-Content response.json
```

You should see a Lambda proxy-style response whose `body` contains:
- `price`

**Note**: the first request can be slower because the Lambda process has to load the PyTorch model into memory.

## Cost Analysis

Your NN Agent:
- **Does not run continuously**: you pay per Lambda invocation and duration
- **Does not use SageMaker**: there is no always-on endpoint cost here
- **Uses a larger Lambda memory size**: memory allocation will affect Lambda cost directly
- **Requires ECR storage**: image storage cost is usually minor compared with invocation cost

## Troubleshooting

If the NN Agent invocation fails:

1. **Check the Lambda logs**:
```bash
aws logs tail /aws/lambda/nn-agent-pricer --follow
```

2. **Verify the runtime configuration**:
```bash
aws lambda get-function-configuration --function-name nn-agent-pricer
```

3. **Verify the image exists in ECR**:
```bash
aws ecr describe-images --repository-name nn-agent-repo --region us-east-1
```

If you changed `project_name`, the repository name will also change.

### Requested Image Not Found

If Lambda cannot find the image tag, the root cause is usually that the ECR repository exists but the tagged image was not pushed yet. Push the image first, then rerun:

```bash
terraform apply
```

### Lambda Times Out or Gets Killed

If inference fails with timeout or memory pressure:
- increase `lambda_timeout`
- increase `lambda_memory_size`
- confirm the image was built successfully with the model file included

The model uses PyTorch and a fairly large hidden layer size, so memory pressure is plausible if you set the Lambda too low.

### Model File Missing

If the logs suggest the model cannot be loaded, confirm that:
- `nn_weights_drive_folder_url` points to a public Google Drive folder that contains a `.pth` file
- your build environment can access Google Drive during `docker buildx build`
- the Docker build context is `../../agents/NNAgent`
- the Dockerfile still downloads from Drive and copies the discovered `.pth` file into Lambda task root as `deep_neural_network_model.bin`

### Docker Build Fails

If `docker buildx build` fails:
- make sure Docker Desktop is running
- confirm you are building from the correct context
- check that your network can pull `public.ecr.aws/lambda/python:3.11`

### Unsupported Manifest or Architecture Errors

If Lambda rejects the image, rebuild and push with:

```bash
docker buildx build --platform linux/amd64 --provenance=false --push -f ../../agents/NNAgent/Dockerfile.lambda -t <ECR_REPOSITORY_URL>:latest ../../agents/NNAgent
```

## Understanding NN vs Specialist

We chose this NN deployment because:
- **It is a compact classical model**: no separate GPU endpoint is required
- **It can run entirely inside Lambda**: the model binary and inference code fit cleanly into a container image
- **It complements the other agents**: the ensemble can combine this deterministic model output with retrieval and specialist outputs

We did **not** use SageMaker here because this model does not need a dedicated managed inference endpoint.

## Operations in AWS

### What to Monitor

For this agent, the important operational signals are:
- **Invocation count**
- **Duration**
- **Error count**
- **Memory usage pressure**, inferred from Lambda failures or throttled behavior
- **Cold start behavior** due to model loading

### Explore in the AWS Console

Navigate to these sections:

1. **AWS Lambda Console**:
   ```
   https://console.aws.amazon.com/lambda/
   ```

2. **Check Your Function**:
   - Open `nn-agent-pricer`
   - Review configuration, image settings, timeout, and memory size

3. **Check CloudWatch Logs**:
   - Open the log group for the NN Agent
   - Review `nn_lambda_success` and `nn_lambda_failure`

4. **Check ECR**:
   - Open the ECR repository for the NN Agent image
   - Confirm the expected tag is present

### Lambda Container vs SageMaker: When to Use Each

| Aspect | Lambda Container | SageMaker |
|--------|------------------|-----------|
| **Use Case** | Small-to-medium self-contained inference workloads | Managed endpoint hosting |
| **This Repo Uses It For** | NN Agent | Specialist and embeddings |
| **Cost Model** | Per invocation | Provisioned endpoint cost |
| **Best For** | Bundled model binaries with moderate runtime needs | Custom hosted models and always-available endpoints |

### Try This: Check Lambda Metrics

While your NN Agent is running, check CloudWatch metrics:

```bash
aws cloudwatch get-metric-statistics --namespace "AWS/Lambda" --metric-name "Invocations" --dimensions Name=FunctionName,Value=nn-agent-pricer --start-time 2026-03-10T00:00:00Z --end-time 2026-03-10T23:59:59Z --period 300 --statistics Sum --region us-east-1
```

This shows how often your NN Agent is being called.

## Clean Up (Optional)

If you need to tear down just the NN Agent infrastructure:

```bash
cd src/terraform/NNAgent
terraform destroy
```

This removes the Lambda function, IAM role, and CloudWatch log group. The ECR repository remains managed by Terraform and will also be destroyed if included in the plan.

## Next Steps

Your NN Agent is ready to serve classical-model price estimates.

Next useful steps are:
1. Test the NN Lambda from the Ensemble Agent path
2. Tune memory and timeout if cold starts are too slow
3. Rebuild and repush the image if you retrain the model binary
4. Deploy the full `src/terraform/Platform` stack if you want all agents wired together automatically
