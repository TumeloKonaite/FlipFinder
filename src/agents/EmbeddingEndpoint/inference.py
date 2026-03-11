import json
import logging
import os
from typing import Any

from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

EMBEDDING_MODEL_ID = os.environ.get(
    "EMBEDDING_MODEL_ID",
    "sentence-transformers/all-MiniLM-L6-v2",
)
EMBEDDING_BATCH_SIZE = int(os.environ.get("EMBEDDING_BATCH_SIZE", "32"))
NORMALIZE_EMBEDDINGS = os.environ.get("NORMALIZE_EMBEDDINGS", "true").lower() in {
    "1",
    "true",
    "yes",
}
TRUST_REMOTE_CODE = os.environ.get("TRUST_REMOTE_CODE", "false").lower() in {
    "1",
    "true",
    "yes",
}
HF_TOKEN = (
    os.environ.get("HF_TOKEN")
    or os.environ.get("HF_API_TOKEN")
    or os.environ.get("HUGGINGFACE_API_TOKEN")
    or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    or None
)
MODEL_DEVICE = os.environ.get("MODEL_DEVICE", "cpu")


def model_fn(model_dir: str) -> dict[str, Any]:
    del model_dir

    logger.info(
        "Loading sentence embedding model %s on device %s",
        EMBEDDING_MODEL_ID,
        MODEL_DEVICE,
    )
    model = SentenceTransformer(
        EMBEDDING_MODEL_ID,
        device=MODEL_DEVICE,
        token=HF_TOKEN,
        trust_remote_code=TRUST_REMOTE_CODE,
    )
    logger.info("Embedding model loaded successfully")
    return {"model": model}


def input_fn(request_body: str | bytes, request_content_type: str) -> dict[str, Any]:
    if not request_content_type.startswith("application/json"):
        raise ValueError(f"Unsupported content type: {request_content_type}")

    if isinstance(request_body, bytes):
        request_body = request_body.decode("utf-8")

    payload = json.loads(request_body)
    inputs = payload.get("inputs")
    if inputs is None:
        raise ValueError("Request payload must contain 'inputs'")

    if isinstance(inputs, str):
        texts = [inputs]
        is_single = True
    elif isinstance(inputs, list) and inputs and all(
        isinstance(item, str) for item in inputs
    ):
        texts = inputs
        is_single = False
    else:
        raise ValueError("'inputs' must be a string or a non-empty list of strings")

    return {"texts": texts, "is_single": is_single}


def predict_fn(
    input_data: dict[str, Any], model_artifacts: dict[str, Any]
) -> list[list[float]] | list[list[list[float]]]:
    model = model_artifacts["model"]
    texts = input_data["texts"]
    is_single = input_data["is_single"]

    embeddings = model.encode(
        texts,
        batch_size=EMBEDDING_BATCH_SIZE,
        convert_to_numpy=True,
        normalize_embeddings=NORMALIZE_EMBEDDINGS,
        show_progress_bar=False,
    )

    if is_single:
        return [embeddings[0].tolist()]

    return [[embedding.tolist()] for embedding in embeddings]


def output_fn(prediction: Any, accept: str) -> tuple[str, str]:
    if not accept:
        accept = "application/json"

    if accept not in ("application/json", "*/*"):
        raise ValueError(f"Unsupported accept type: {accept}")
    return json.dumps(prediction), "application/json"
