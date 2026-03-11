import json
import os
import random
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Lock

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError, ReadTimeoutError
from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env", override=False)

LITE_MODE = True
AWS_REGION = "us-east-1"
SOURCE_BUCKET = "my-product-data-194722416872"
DATASET_NAME = "items_lite" if LITE_MODE else "items_full"
SOURCE_KEY = f"{DATASET_NAME}/train.jsonl"
VECTOR_BUCKET = "products-vectors-194722416872"
INDEX_NAME = "products-lite" if LITE_MODE else "products"
DEFAULT_SAGEMAKER_ENDPOINT = os.getenv(
    "SAGEMAKER_ENDPOINT",
    "flipfinder-embedding-endpoint",
)


def int_env(name, default):
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def parse_endpoint_names():
    raw_value = os.getenv("SAGEMAKER_ENDPOINTS")
    if raw_value:
        endpoints = [item.strip() for item in raw_value.split(",") if item.strip()]
        if endpoints:
            return endpoints
    return [DEFAULT_SAGEMAKER_ENDPOINT]


SAGEMAKER_ENDPOINTS = parse_endpoint_names()
PUT_BATCH_SIZE = max(1, int_env("VECTOR_PUT_BATCH_SIZE", 128))
EMBED_BATCH_SIZE = max(1, int_env("VECTOR_EMBED_BATCH_SIZE", 8))
DEFAULT_MAX_WORKERS = max(2, min(len(SAGEMAKER_ENDPOINTS) * 2, 8))
MAX_WORKERS = max(1, int_env("VECTOR_MAX_WORKERS", DEFAULT_MAX_WORKERS))
EMBED_MAX_RETRIES = max(1, int_env("VECTOR_EMBED_MAX_RETRIES", 4))
SAGEMAKER_CONNECT_TIMEOUT = max(1, int_env("SAGEMAKER_CONNECT_TIMEOUT_SECONDS", 10))
SAGEMAKER_READ_TIMEOUT = max(1, int_env("SAGEMAKER_READ_TIMEOUT_SECONDS", 180))


session = boto3.session.Session(region_name=AWS_REGION)
s3 = session.client(
    "s3",
    config=Config(retries={"max_attempts": 10, "mode": "adaptive"}),
)
s3_vectors = session.client("s3vectors")
sagemaker_runtime = session.client(
    "sagemaker-runtime",
    config=Config(
        retries={"max_attempts": 2, "mode": "adaptive"},
        connect_timeout=SAGEMAKER_CONNECT_TIMEOUT,
        read_timeout=SAGEMAKER_READ_TIMEOUT,
    ),
)
endpoint_lock = Lock()
endpoint_index = 0


def extract_embedding(result):
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, list) and first:
            if isinstance(first[0], list):
                return [float(value) for value in first[0]]
            return [float(value) for value in first]
        return [float(value) for value in result]
    raise ValueError("Unexpected embedding payload from SageMaker")


def chunked(items, size):
    for index in range(0, len(items), size):
        yield items[index : index + size]


def next_embedding_endpoint():
    global endpoint_index

    if len(SAGEMAKER_ENDPOINTS) == 1:
        return SAGEMAKER_ENDPOINTS[0]

    with endpoint_lock:
        endpoint_name = SAGEMAKER_ENDPOINTS[endpoint_index % len(SAGEMAKER_ENDPOINTS)]
        endpoint_index += 1
        return endpoint_name


def invoke_embedding_batch(texts, endpoint_name):
    payload = {"inputs": texts if len(texts) > 1 else texts[0]}
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=endpoint_name,
        ContentType="application/json",
        Body=json.dumps(payload),
    )
    result = json.loads(response["Body"].read().decode("utf-8"))

    if len(texts) == 1:
        return [extract_embedding(result)]

    if not isinstance(result, list) or len(result) != len(texts):
        raise ValueError("Unexpected batch embedding payload from SageMaker")

    return [extract_embedding(item) for item in result]


def is_retryable_embedding_error(error):
    if isinstance(error, ReadTimeoutError):
        return True

    if isinstance(error, BotoCoreError):
        return True

    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        return code in {
            "InternalFailure",
            "InternalServerException",
            "ModelError",
            "ModelNotReadyException",
            "ServiceUnavailable",
            "ThrottlingException",
        }

    return False


def describe_embedding_error(error):
    if isinstance(error, ClientError):
        details = error.response.get("Error", {})
        code = details.get("Code", type(error).__name__)
        message = details.get("Message")
        return f"{code}: {message}" if message else code
    return str(error) or type(error).__name__


def get_embeddings(texts):
    last_error = None

    for attempt in range(EMBED_MAX_RETRIES):
        endpoint_name = next_embedding_endpoint()
        try:
            return invoke_embedding_batch(texts, endpoint_name)
        except Exception as error:
            last_error = error

            if not is_retryable_embedding_error(error):
                raise

            if attempt == EMBED_MAX_RETRIES - 1:
                break

            delay_seconds = min(2**attempt, 20) + random.uniform(0, 0.5)
            print(
                f"Embedding request failed on {endpoint_name} for batch size "
                f"{len(texts)} "
                f"({describe_embedding_error(error)}); retrying in "
                f"{delay_seconds:.1f}s ({attempt + 1}/{EMBED_MAX_RETRIES})"
            )
            time.sleep(delay_seconds)

    if len(texts) == 1:
        raise last_error

    if len(texts) == 2:
        return [get_embeddings([text])[0] for text in texts]

    midpoint = len(texts) // 2
    print(
        f"Splitting embedding batch of size {len(texts)} after "
        f"{EMBED_MAX_RETRIES} failed attempts"
    )
    left = get_embeddings(texts[:midpoint])
    right = get_embeddings(texts[midpoint:])
    return left + right


def ensure_vector_bucket():
    try:
        s3_vectors.get_vector_bucket(vectorBucketName=VECTOR_BUCKET)
        return
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "NotFoundException":
            raise

    print(f"Creating vector bucket: {VECTOR_BUCKET}")
    s3_vectors.create_vector_bucket(vectorBucketName=VECTOR_BUCKET)


def ensure_index(dimension):
    try:
        response = s3_vectors.get_index(
            vectorBucketName=VECTOR_BUCKET,
            indexName=INDEX_NAME,
        )
        index = response["index"]
        if index["dimension"] != dimension:
            raise RuntimeError(
                f"Index {INDEX_NAME} already exists with dimension {index['dimension']}, "
                f"but this endpoint returns dimension {dimension}."
            )
        return
    except ClientError as error:
        if error.response.get("Error", {}).get("Code") != "NotFoundException":
            raise

    print(f"Creating vector index: {INDEX_NAME}")
    s3_vectors.create_index(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        dataType="float32",
        dimension=dimension,
        distanceMetric="cosine",
        metadataConfiguration={
            "nonFilterableMetadataKeys": ["text", "source_uri"]
        },
    )

    for _ in range(30):
        try:
            s3_vectors.get_index(
                vectorBucketName=VECTOR_BUCKET,
                indexName=INDEX_NAME,
            )
            return
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") != "NotFoundException":
                raise
            time.sleep(2)

    raise TimeoutError(f"Timed out waiting for index {INDEX_NAME} to become ready")


def put_batch(batch):
    text_batches = list(chunked([item["text"] for item in batch], EMBED_BATCH_SIZE))
    embeddings = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        for result in executor.map(get_embeddings, text_batches):
            embeddings.extend(result)

    vectors = []

    for item, embedding in zip(batch, embeddings, strict=True):
        vectors.append(
            {
                "key": item["key"],
                "data": {"float32": embedding},
                "metadata": item["metadata"],
            }
        )

    s3_vectors.put_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        vectors=vectors,
    )


def iter_s3_jsonl_lines(bucket, key, chunk_size=1024 * 1024, max_retries=8):
    start_byte = 0
    pending = b""
    retries = 0

    while True:
        response = None
        try:
            request = {"Bucket": bucket, "Key": key}
            if start_byte:
                request["Range"] = f"bytes={start_byte}-"

            response = s3.get_object(**request)
            body = response["Body"]

            for chunk in body.iter_chunks(chunk_size=chunk_size):
                if not chunk:
                    continue

                retries = 0
                start_byte += len(chunk)
                pending += chunk

                while True:
                    newline_index = pending.find(b"\n")
                    if newline_index == -1:
                        break

                    line = pending[:newline_index].rstrip(b"\r")
                    pending = pending[newline_index + 1 :]
                    if line:
                        yield line

            if pending.strip():
                yield pending.rstrip(b"\r")
            return
        except (BotoCoreError, ClientError) as error:
            retries += 1
            if retries > max_retries:
                raise RuntimeError(
                    f"Failed to stream s3://{bucket}/{key} after {max_retries} retries"
                ) from error

            delay_seconds = min(2**retries, 30)
            print(
                f"S3 stream interrupted at byte {start_byte:,}; retrying in "
                f"{delay_seconds}s ({retries}/{max_retries})"
            )
            time.sleep(delay_seconds)
        finally:
            if response is not None:
                response["Body"].close()


def main():
    print(f"Reading s3://{SOURCE_BUCKET}/{SOURCE_KEY}")
    print(f"Embedding endpoints: {', '.join(SAGEMAKER_ENDPOINTS)}")
    print(
        f"Embedding config: batch_size={EMBED_BATCH_SIZE}, "
        f"workers={MAX_WORKERS}, retries={EMBED_MAX_RETRIES}"
    )

    batch = []
    total = 0
    index_ready = False

    for line_number, raw_line in enumerate(
        iter_s3_jsonl_lines(SOURCE_BUCKET, SOURCE_KEY), start=1
    ):
        row = json.loads(raw_line.decode("utf-8"))
        text = (row.get("summary") or "").strip()
        if not text:
            continue

        batch.append(
            {
                "key": f"train:{line_number}",
                "text": text,
                "metadata": {
                    "text": text,
                    "category": row.get("category"),
                    "price": float(row["price"]) if row.get("price") is not None else None,
                    "source_uri": f"s3://{SOURCE_BUCKET}/{SOURCE_KEY}",
                    "line_number": line_number,
                },
            }
        )

        if len(batch) < PUT_BATCH_SIZE:
            continue

        if not index_ready:
            ensure_vector_bucket()
            sample_embedding = get_embeddings([batch[0]["text"]])[0]
            ensure_index(len(sample_embedding))
            index_ready = True

        put_batch(batch)
        total += len(batch)
        print(f"Ingested {total:,} vectors")
        batch = []

    if batch:
        if not index_ready:
            ensure_vector_bucket()
            sample_embedding = get_embeddings([batch[0]["text"]])[0]
            ensure_index(len(sample_embedding))
            index_ready = True

        put_batch(batch)
        total += len(batch)
        print(f"Ingested {total:,} vectors")

    print()
    print(f"Finished ingesting {total:,} vectors")
    print(f"Vector bucket: {VECTOR_BUCKET}")
    print(f"Vector index:  {INDEX_NAME}")


if __name__ == "__main__":
    main()
