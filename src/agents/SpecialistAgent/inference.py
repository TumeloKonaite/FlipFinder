import json
import logging
import os
import re
from typing import Any

import torch
from peft import PeftConfig, PeftModel
from transformers import (
    AutoModelForCausalLM,
    AutoTokenizer,
    BitsAndBytesConfig,
    set_seed,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

BASE_MODEL = os.environ.get("BASE_MODEL", "Qwen/Qwen2.5-3B-Instruct")
FINETUNED_MODEL = os.environ["FINETUNED_MODEL"]
REVISION = os.environ.get("MODEL_REVISION", "").strip() or None

QUESTION = os.environ.get("QUESTION", "What does this cost to the nearest dollar?")
PREFIX = os.environ.get("PREFIX", "Price is $")
MAX_NEW_TOKENS = int(os.environ.get("MAX_NEW_TOKENS", "5"))
SEED = int(os.environ.get("SEED", "42"))
ENABLE_4BIT = os.environ.get("ENABLE_4BIT", "false").lower() in ("1", "true", "yes")
HF_TOKEN = (
    os.environ.get("HF_TOKEN")
    or os.environ.get("HF_API_TOKEN")
    or os.environ.get("HUGGINGFACE_API_TOKEN")
    or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    or None
)

MODEL_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"


def _ensure_hf_auth_if_needed() -> None:
    gated_prefixes = ("meta-llama/",)
    gated_repos = [
        repo
        for repo in (BASE_MODEL, FINETUNED_MODEL)
        if any(repo.startswith(prefix) for prefix in gated_prefixes)
    ]
    if gated_repos and not HF_TOKEN:
        joined = ", ".join(gated_repos)
        raise RuntimeError(
            "Hugging Face authentication is required for the configured model repo(s): "
            f"{joined}. Set HF_TOKEN/HUGGINGFACE_API_TOKEN or Terraform "
            "variable huggingface_api_token before deploying."
        )


def _build_quant_config() -> BitsAndBytesConfig:
    return BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,
        bnb_4bit_quant_type="nf4",
    )


def _load_tokenizer(model_name: str, fallback_model_name: str | None = None) -> Any:
    try:
        logger.info("Loading tokenizer from %s", model_name)
        return AutoTokenizer.from_pretrained(model_name, revision=REVISION, token=HF_TOKEN)
    except Exception:
        if not fallback_model_name:
            raise
        logger.info("Falling back to tokenizer from %s", fallback_model_name)
        return AutoTokenizer.from_pretrained(
            fallback_model_name,
            revision=REVISION,
            token=HF_TOKEN,
        )


def _load_model_with_fallback(model_name: str) -> Any:
    base_kwargs: dict[str, Any] = {
        "revision": REVISION,
        "token": HF_TOKEN,
    }

    if MODEL_DEVICE == "cuda":
        base_kwargs["device_map"] = "auto"
        base_kwargs["dtype"] = torch.float16
    else:
        base_kwargs["device_map"] = "cpu"
        base_kwargs["dtype"] = torch.float32

    if ENABLE_4BIT and MODEL_DEVICE == "cuda":
        try:
            return AutoModelForCausalLM.from_pretrained(
                model_name,
                quantization_config=_build_quant_config(),
                **base_kwargs,
            )
        except Exception as exc:
            logger.warning(
                "4-bit model load failed for %s; retrying without quantization: %s",
                model_name,
                exc,
            )

    return AutoModelForCausalLM.from_pretrained(
        model_name,
        **base_kwargs,
    )


def _load_direct_model() -> tuple[Any, Any]:
    tokenizer = _load_tokenizer(FINETUNED_MODEL, BASE_MODEL)

    logger.info("Loading fine-tuned model directly from %s", FINETUNED_MODEL)
    model = _load_model_with_fallback(FINETUNED_MODEL)
    return tokenizer, model


def _load_adapter_model(adapter_config: PeftConfig) -> tuple[Any, Any]:
    adapter_base_model = getattr(adapter_config, "base_model_name_or_path", "") or BASE_MODEL
    if adapter_base_model != BASE_MODEL:
        logger.info(
            "Adapter base model %s overrides configured BASE_MODEL %s",
            adapter_base_model,
            BASE_MODEL,
        )

    tokenizer = _load_tokenizer(adapter_base_model)

    logger.info("Loading adapter base model from %s", adapter_base_model)
    base_model = _load_model_with_fallback(adapter_base_model)

    logger.info(
        "Loading PEFT adapter from %s revision=%s",
        FINETUNED_MODEL,
        REVISION,
    )

    model = PeftModel.from_pretrained(
        base_model,
        FINETUNED_MODEL,
        revision=REVISION,
        token=HF_TOKEN,
    )
    return tokenizer, model


def _is_missing_adapter_metadata_error(exc: Exception) -> bool:
    text = str(exc).lower()
    adapter_markers = (
        "adapter_config.json",
        "can't find 'adapter_config.json'",
        "can't find adapter_config.json",
        "does not appear to have a file named adapter_config.json",
        "is not a valid peft model",
    )
    return any(marker in text for marker in adapter_markers)


def model_fn(model_dir: str) -> dict[str, Any]:
    """
    SageMaker-style model loader.
    model_dir is unused here because we load from Hugging Face directly.
    """
    _ensure_hf_auth_if_needed()
    try:
        adapter_config = PeftConfig.from_pretrained(
            FINETUNED_MODEL,
            revision=REVISION,
            token=HF_TOKEN,
        )
        logger.info("Detected PEFT adapter repo: %s", FINETUNED_MODEL)
        tokenizer, model = _load_adapter_model(adapter_config)
    except Exception as exc:
        if not _is_missing_adapter_metadata_error(exc):
            logger.exception(
                "Failed while probing/loading PEFT adapter repo %s",
                FINETUNED_MODEL,
            )
            raise

        logger.info(
            "Repo %s does not expose PEFT adapter metadata; loading as a standalone "
            "fine-tuned model. Details: %s",
            FINETUNED_MODEL,
            exc,
        )
        tokenizer, model = _load_direct_model()

    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model.eval()

    logger.info("Model loaded successfully")
    return {
        "tokenizer": tokenizer,
        "model": model,
    }


def input_fn(request_body: str | bytes, request_content_type: str) -> dict[str, Any]:
    if not request_content_type.startswith("application/json"):
        raise ValueError(f"Unsupported content type: {request_content_type}")

    if isinstance(request_body, bytes):
        request_body = request_body.decode("utf-8")

    payload = json.loads(request_body)

    if "description" not in payload:
        raise ValueError("Request payload must contain 'description'")

    return payload


def _extract_price(text: str) -> float:
    if PREFIX in text:
        text = text.split(PREFIX, 1)[1]

    text = text.replace(",", "")
    match = re.search(r"[-+]?\d*\.\d+|\d+", text)
    return float(match.group()) if match else 0.0


def predict_fn(input_data: dict[str, Any], model_artifacts: dict[str, Any]) -> dict[str, Any]:
    description = input_data["description"]

    tokenizer = model_artifacts["tokenizer"]
    model = model_artifacts["model"]

    set_seed(SEED)
    prompt = f"{QUESTION}\n\n{description}\n\n{PREFIX}"

    encoded = tokenizer(prompt, return_tensors="pt")
    model_device = next(model.parameters()).device
    encoded = {key: value.to(model_device) for key, value in encoded.items()}

    with torch.no_grad():
        outputs = model.generate(
            **encoded,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
        )

    decoded = tokenizer.decode(outputs[0], skip_special_tokens=True)
    price = _extract_price(decoded)

    return {
        "price": price,
        "raw_output": decoded,
    }


def output_fn(prediction: dict[str, Any], accept: str) -> tuple[str, str]:
    if accept not in ("application/json", "*/*"):
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps(prediction), "application/json"
