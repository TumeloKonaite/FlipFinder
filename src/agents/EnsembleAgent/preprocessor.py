import logging
import os
import re
import time

import boto3

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args, **kwargs):
        return False

load_dotenv(override=True)
logger = logging.getLogger(__name__)

DEFAULT_MODEL_NAME = os.getenv(
    "PRICER_PREPROCESSOR_MODEL",
    "bedrock/converse/openai.gpt-oss-120b-1:0",
)
DEFAULT_REASONING_EFFORT = "low" if "gpt-oss" in DEFAULT_MODEL_NAME else None
MAX_PREPROCESS_ATTEMPTS = 3
FIELD_ORDER = ("Title", "Category", "Brand", "Description", "Details")

SYSTEM_PROMPT = """Create a concise description of a product. Respond only in this format. Do not include part numbers.
Title: Rewritten short precise title
Category: eg Electronics
Brand: Brand name
Description: 1 sentence description
Details: 1 sentence on features"""


class Preprocessor:
    def __init__(
        self,
        model_name=DEFAULT_MODEL_NAME,
        reasoning_effort=DEFAULT_REASONING_EFFORT,
    ):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cost = 0
        self.model_name = model_name
        self.reasoning_effort = reasoning_effort

        if self.model_name.startswith("bedrock/"):
            os.environ.setdefault(
                "AWS_REGION_NAME",
                os.getenv("BEDROCK_AWS_REGION")
                or os.getenv("FRONTIER_AWS_REGION")
                or os.getenv("DEFAULT_AWS_REGION")
                or os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or "us-east-1",
            )
            self.bedrock_runtime = boto3.client(
                "bedrock-runtime",
                region_name=(
                    os.getenv("BEDROCK_AWS_REGION")
                    or os.getenv("FRONTIER_AWS_REGION")
                    or os.getenv("DEFAULT_AWS_REGION")
                    or os.getenv("AWS_REGION")
                    or os.getenv("AWS_DEFAULT_REGION")
                    or "us-east-1"
                ),
            )
        else:
            self.bedrock_runtime = None

    def messages_for(self, text: str) -> list[dict]:
        return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": text}]

    def _extract_fields(self, response_text: str) -> dict[str, str]:
        fields: dict[str, str] = {}
        for raw_line in response_text.splitlines():
            line = raw_line.strip()
            if not line or ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            if key in FIELD_ORDER and key not in fields:
                fields[key] = value.strip()
        return fields

    def _normalize_response(self, fields: dict[str, str]) -> str:
        return "\n".join(f"{key}: {fields[key]}" for key in FIELD_ORDER)

    def _validation_errors(self, fields: dict[str, str]) -> list[str]:
        errors = [field for field in FIELD_ORDER if not fields.get(field)]
        if fields.get("Title", "").endswith(":"):
            errors.append("Title")
        return sorted(set(errors))

    def _fallback_response(self, text: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        title = compact[:80] if compact else "Unknown product"
        return "\n".join(
            [
                f"Title: {title}",
                "Category: Unknown",
                "Brand: Unknown",
                f"Description: {compact or 'No description provided.'}",
                "Details: Additional details were unavailable from the model response.",
            ]
        )

    def _bedrock_model_id(self) -> str:
        if self.model_name.startswith("bedrock/converse/"):
            return self.model_name.removeprefix("bedrock/converse/")
        if self.model_name.startswith("bedrock/"):
            return self.model_name.removeprefix("bedrock/")
        return self.model_name

    def _preprocess_with_bedrock(self, text: str, retry_errors: list[str] | None = None) -> str:
        user_text = text
        if retry_errors:
            missing = ", ".join(retry_errors)
            user_text = (
                f"{text}\n\n"
                f"Your previous answer was invalid because these fields were missing or blank: {missing}. "
                "Return exactly one non-empty line for each of Title, Category, Brand, Description, and Details."
            )

        response = self.bedrock_runtime.converse(
            modelId=self._bedrock_model_id(),
            system=[{"text": SYSTEM_PROMPT}],
            messages=[
                {
                    "role": "user",
                    "content": [{"text": user_text}],
                }
            ],
            inferenceConfig={
                "maxTokens": 300,
                "temperature": 0.1,
            },
        )

        usage = response.get("usage", {})
        self.total_input_tokens += usage.get("inputTokens", 0)
        self.total_output_tokens += usage.get("outputTokens", 0)
        content = response["output"]["message"]["content"]
        return "".join(block.get("text", "") for block in content).strip()

    def preprocess(self, text: str) -> str:
        if self.model_name.startswith("bedrock/"):
            retry_errors = None
            for attempt in range(1, MAX_PREPROCESS_ATTEMPTS + 1):
                started = time.perf_counter()
                result = self._preprocess_with_bedrock(text, retry_errors=retry_errors)
                latency_ms = round((time.perf_counter() - started) * 1000, 2)
                fields = self._extract_fields(result)
                retry_errors = self._validation_errors(fields)
                if not retry_errors:
                    normalized = self._normalize_response(fields)
                    logger.info(
                        "preprocessor_success attempt=%s latency_ms=%s model=%s",
                        attempt,
                        latency_ms,
                        self.model_name,
                    )
                    return normalized

                logger.warning(
                    "preprocessor_invalid_response attempt=%s latency_ms=%s missing_fields=%s raw=%r",
                    attempt,
                    latency_ms,
                    ",".join(retry_errors),
                    result[:500],
                )

            fallback = self._fallback_response(text)
            logger.error(
                "preprocessor_fallback model=%s fallback=%r",
                self.model_name,
                fallback,
            )
            return fallback

        raise RuntimeError(
            "Preprocessor only supports Bedrock models in the AWS Lambda runtime"
        )
