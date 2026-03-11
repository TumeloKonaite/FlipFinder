# FlipFinder

FlipFinder is a multi-agent pricing system for e-commerce deal discovery. It combines:
- retrieval-based pricing (`FrontierAgent`)
- custom model inference (`SpecialistAgent` on SageMaker)
- classical neural network inference (`NNAgent` in Lambda container)
- orchestration (`EnsembleAgent` and `PlanningAgent`)
- deal scanning (`ScannerAgent`)

The infrastructure is deployed with Terraform. The top-level deployment path is:
- `src/terraform/Platform`

This README is optimized for the flow:
1. clone repo
2. add API keys / model settings
3. run `terraform apply` from `Platform`

## Architecture

Core runtime components:
- `EmbeddingEndpoint` (SageMaker serverless): sentence embeddings
- `SpecialistAgent` (SageMaker realtime + Lambda wrapper): fine-tuned model pricing
- `NNAgent` (Lambda container): local PyTorch model pricing
- `FrontierAgent` (Lambda): embedding + S3 Vectors retrieval + OpenAI pricing
- `EnsembleAgent` (Lambda): weighted combination of Frontier/Specialist/NN
- `ScannerAgent` (Lambda + EventBridge + DynamoDB): periodic deal scan
- `PlanningAgent` (Lambda + SNS): orchestrates scanning/pricing/alerting

High-level request path:
1. Scanner finds candidate deals
2. Ensemble preprocesses and fans out to Frontier/Specialist/NN
3. Ensemble returns weighted price
4. Planning applies threshold logic and sends SNS alerts

## Repository Layout

Top-level directories:
- `src/agents/` agent implementations
- `src/terraform/` Terraform modules
- `src/dataset_ingestion/` product ingestion scripts for S3 + S3 Vectors
- `docs/` deployment guides per component
- `scripts/` operational utilities (for example smoke tests)
- `notebooks/` experimentation and data prep notebooks

Most important Terraform path:
- `src/terraform/Platform`

## Prerequisites

Required:
- AWS account + credentials configured in CLI
- Terraform `>= 1.5`
- Docker with buildx
- Python `>= 3.12`
- AWS IAM permissions for Lambda, ECR, SageMaker, IAM, CloudWatch, EventBridge, DynamoDB, SNS, Bedrock, S3 Vectors

Recommended local tools:
- `uv` (optional) or `pip`
- GitHub Actions is already configured with `.github/workflows/ci.yml`

Notes:
- Terraform packaging/build scripts are currently Windows-oriented (`cmd`/PowerShell for `local-exec`).
- NN model weights are downloaded during Docker build from Google Drive (configurable variable).

## Quick Start (Local Python)

Using `uv`:

```bash
uv sync
```

Using `pip`:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Deploy Full Stack with Terraform Platform

### 1. Open Platform module

```bash
cd src/terraform/Platform
```

### 2. Create `terraform.tfvars`

Copy the example:

```bash
copy terraform.tfvars.example terraform.tfvars
```

PowerShell alternative:

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

### 3. Set required values

At minimum set:
- `specialist_finetuned_model` (required, no default)
- OpenAI credential strategy:
  - `openai_api_key`, or
  - `openai_api_key_secret_arn`, or
  - `openai_api_key_ssm_parameter_name`
- `huggingface_api_token` if base/fine-tuned model repos are gated

Important defaults in example:
- `nn_weights_drive_folder_url` points to your Week 6 Google Drive folder
- `auto_build_container_images = true`

If you already have a populated vector index, set:
- `frontier_vector_bucket`
- `frontier_index_name`

Configuration checklist:

| Variable | Required for `terraform apply` | Required for working runtime | Notes |
|---|---|---|---|
| `specialist_finetuned_model` | Yes | Yes | No default; apply fails without it |
| `openai_api_key` or `openai_api_key_secret_arn` or `openai_api_key_ssm_parameter_name` | No | Yes (Frontier/Scanner) | Prefer secret ARN or SSM over plain key |
| `huggingface_api_token` | No | Sometimes | Needed when base/fine-tuned repos are gated |
| `nn_weights_drive_folder_url` | No (default provided) | Yes (NN image build) | Folder must be accessible and contain a `.pth` file |
| `frontier_vector_bucket` / `frontier_index_name` | No (defaults exist) | Yes (Frontier quality) | Must point to populated S3 Vectors index |
| `messaging_email_endpoint` | No | Optional | If set, confirm SNS email subscription |

Minimal `terraform.tfvars` example:

```hcl
aws_region     = "us-east-1"
project_prefix = "pricing"

specialist_finetuned_model = "TumeloKonaite/<your-price-model-repo>"

# Choose ONE OpenAI strategy:
openai_api_key                    = ""
openai_api_key_secret_arn         = "arn:aws:secretsmanager:us-east-1:123456789012:secret:openai-key"
openai_api_key_ssm_parameter_name = ""

huggingface_api_token       = ""
nn_weights_drive_folder_url = "https://drive.google.com/drive/folders/1uq5C9edPIZ1973dArZiEO-VE13F7m8MK?usp=drive_link"
```

### 4. Deploy

```bash
terraform init
terraform apply
```

This single apply wires all modules:
- Embedding endpoint
- NN, Specialist, Frontier, Ensemble, Scanner, Planning

### 5. Capture outputs

After apply:

```bash
terraform output
```

Use outputs for Lambda names, embedding endpoint name, SNS topic, etc.

## Secrets and Safety

This repo is configured to avoid committing local secrets/state:
- `.env` and `.env.*` ignored
- `*.tfvars` ignored (except `*.tfvars.example`)
- `*.tfstate*` ignored
- generated lambda zips/build folders ignored

Do not store real secrets in tracked files. Use:
- AWS Secrets Manager (`openai_api_key_secret_arn`) or
- SSM SecureString (`openai_api_key_ssm_parameter_name`)

## Post-Deploy Steps (Important)

`terraform apply` builds infra, but a fully working system also needs:

1. **S3 Vectors ingestion**
   - Follow [docs/DataIngestion.md](docs/DataIngestion.md)
   - Ensure `frontier_vector_bucket` and `frontier_index_name` match ingested targets

2. **SNS email confirmation**
   - If `messaging_email_endpoint` is set, confirm subscription from inbox

3. **Model/runtime verification**
   - Specialist endpoint can take time to warm up
   - Ensure OpenAI and HF credentials are valid

## Smoke Test

Run the Lambda smoke test after deploy:

```bash
python scripts/smoke_test_agents.py --region us-east-1
```

Optional explicit function names:

```bash
python scripts/smoke_test_agents.py ^
  --frontier pricing-frontier-agent-pricer ^
  --specialist pricing-specialist-wrapper ^
  --nn pricing-nn-agent-pricer ^
  --ensemble pricing-ensemble-orchestrator
```

The script prints a JSON summary including status and latency for each agent.

## Detailed Component Docs

- [docs/EmbeddingEndpoint.md](docs/EmbeddingEndpoint.md)
- [docs/SpecialistAgent.md](docs/SpecialistAgent.md)
- [docs/NNAgent.md](docs/NNAgent.md)
- [docs/FrontierAgent.md](docs/FrontierAgent.md)
- [docs/EnsembleAgent.md](docs/EnsembleAgent.md)
- [docs/ScannerAgent.md](docs/ScannerAgent.md)
- [docs/PlanningAgent.md](docs/PlanningAgent.md)
- [docs/DataIngestion.md](docs/DataIngestion.md)
- [docs/MessangingAgent.md](docs/MessangingAgent.md)

## Common Failure Points

- Docker build fails:
  - ensure Docker Desktop/buildx is available
  - verify network can access base images and Google Drive weights URL

- Terraform apply succeeds but runtime fails:
  - missing OpenAI credentials
  - missing SNS subscription confirmation
  - empty/mismatched S3 Vectors index for Frontier

- Specialist inference errors:
  - verify base + fine-tuned model compatibility
  - verify HF token access if repos are gated

## Destroy / Cleanup

From `src/terraform/Platform`:

```bash
terraform destroy
```

If buckets/endpoints/images are protected or in use, resolve those dependencies first.

## License

See [LICENSE](LICENSE).
