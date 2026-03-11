"""
Test script for searching the product S3 Vectors index.
"""

import json
import os
from pathlib import Path

import boto3
from dotenv import load_dotenv


env_path = Path(__file__).parent.parent.parent / ".env"
load_dotenv(env_path, override=True)

AWS_REGION = os.getenv("FRONTIER_AWS_REGION", "us-east-1")
VECTOR_BUCKET = os.getenv("FRONTIER_VECTOR_BUCKET", "products-vectors-194722416872")
SAGEMAKER_ENDPOINT = os.getenv("FRONTIER_SAGEMAKER_ENDPOINT", "flipfinder-embedding-endpoint")
INDEX_NAME = os.getenv("FRONTIER_INDEX_NAME", "products")

s3_vectors = boto3.client("s3vectors", region_name=AWS_REGION)
sagemaker_runtime = boto3.client("sagemaker-runtime", region_name=AWS_REGION)


def get_embedding(text):
    response = sagemaker_runtime.invoke_endpoint(
        EndpointName=SAGEMAKER_ENDPOINT,
        ContentType="application/json",
        Body=json.dumps({"inputs": text}),
    )

    result = json.loads(response["Body"].read().decode())
    if isinstance(result, list) and result:
        if isinstance(result[0], list) and result[0]:
            if isinstance(result[0][0], list):
                return result[0][0]
            return result[0]
    return result


def list_sample_vectors():
    print(f"Listing sample vectors in bucket: {VECTOR_BUCKET}, index: {INDEX_NAME}")
    print("=" * 60)

    response = s3_vectors.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": get_embedding("consumer product")},
        topK=10,
        returnDistance=True,
        returnMetadata=True,
    )

    vectors = response.get("vectors", [])
    print(f"\nFound {len(vectors)} sample vectors:\n")

    for i, vector in enumerate(vectors, 1):
        metadata = vector.get("metadata", {})
        text = metadata.get("text", "")
        preview = text[:100] + "..." if len(text) > 100 else text

        print(f"{i}. Vector ID: {vector['key']}")
        if metadata.get("category"):
            print(f"   Category: {metadata['category']}")
        if metadata.get("price") is not None:
            print(f"   Price: ${float(metadata['price']):.2f}")
        print(f"   Text: {preview}")
        print()


def search_vectors(query_text, k=5):
    print(f"\nSearching for: '{query_text}'")
    print("-" * 40)

    query_embedding = get_embedding(query_text)
    response = s3_vectors.query_vectors(
        vectorBucketName=VECTOR_BUCKET,
        indexName=INDEX_NAME,
        queryVector={"float32": query_embedding},
        topK=k,
        returnDistance=True,
        returnMetadata=True,
    )

    vectors = response.get("vectors", [])
    print(f"Found {len(vectors)} results:\n")

    for vector in vectors:
        metadata = vector.get("metadata", {})
        distance = vector.get("distance", 0)

        print(f"Score: {1 - distance:.3f}")
        if metadata.get("category"):
            print(f"Category: {metadata['category']}")
        if metadata.get("price") is not None:
            print(f"Price: ${float(metadata['price']):.2f}")
        print(f"Text: {metadata.get('text', '')[:200]}...")
        print()


def main():
    print("=" * 60)
    print("Product S3 Vectors Database Explorer")
    print("=" * 60)
    print(f"Region: {AWS_REGION}")
    print(f"Bucket: {VECTOR_BUCKET}")
    print(f"Index: {INDEX_NAME}")
    print(f"Embedding Endpoint: {SAGEMAKER_ENDPOINT}")
    print()

    list_sample_vectors()

    print("=" * 60)
    print("Example Semantic Searches")
    print("=" * 60)

    search_queries = [
        "wireless noise cancelling headphones",
        "stainless steel kitchen mixer",
        "gaming laptop with RTX graphics",
    ]

    for query in search_queries:
        search_vectors(query, k=3)

    print("\nSemantic search test complete.")


if __name__ == "__main__":
    main()
