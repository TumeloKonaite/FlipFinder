import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List, Dict

import boto3
from dotenv import load_dotenv
from openai import OpenAI
from src.agents.agent import Agent


ROOT_DIR = Path(__file__).resolve().parents[3]
load_dotenv(ROOT_DIR / ".env", override=False)
logger = logging.getLogger(__name__)


class FrontierAgent(Agent):
    name = "Frontier Agent"
    color = Agent.BLUE

    MODEL = "gpt-4o-mini"

    def __init__(self):
        """
        Set up this instance with OpenAI plus AWS services for RAG.
        """
        self.log("Initializing Frontier Agent")
        self.MODEL = os.getenv("FRONTIER_MODEL", "gpt-5.1")
        self.aws_region = (
            os.getenv("FRONTIER_AWS_REGION")
            or os.getenv("DEFAULT_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.vector_bucket = os.getenv(
            "FRONTIER_VECTOR_BUCKET",
            os.getenv("VECTOR_BUCKET", "products-vectors-194722416872"),
        )
        self.index_name = os.getenv(
            "FRONTIER_INDEX_NAME",
            os.getenv("INDEX_NAME", "products"),
        )
        self.embedding_endpoint = os.getenv(
            "FRONTIER_SAGEMAKER_ENDPOINT",
            "flipfinder-embedding-endpoint",
        )
        self.top_k = int(os.getenv("FRONTIER_TOP_K", "5"))
        session = boto3.session.Session(region_name=self.aws_region)
        self.session = session
        self.sagemaker_runtime = session.client("sagemaker-runtime")
        self.s3_vectors = session.client("s3vectors")
        self.client = OpenAI(api_key=self._load_openai_api_key())
        self.log(f"Frontier Agent is using OpenAI model {self.MODEL}")
        self.log("Frontier Agent is ready")

    def _load_openai_api_key(self) -> str:
        direct = os.getenv("OPENAI_API_KEY", "").strip()
        if direct:
            return direct

        secret_arn = os.getenv("OPENAI_API_KEY_SECRET_ARN", "").strip()
        if secret_arn:
            secret_value = self.session.client("secretsmanager").get_secret_value(
                SecretId=secret_arn
            )
            secret_string = secret_value.get("SecretString", "")
            if not secret_string:
                raise RuntimeError("Secrets Manager secret did not contain SecretString")
            try:
                payload = json.loads(secret_string)
            except json.JSONDecodeError:
                return secret_string.strip()

            for key in ("OPENAI_API_KEY", "openai_api_key", "api_key"):
                value = payload.get(key)
                if value:
                    return str(value).strip()
            raise RuntimeError("Secrets Manager secret did not contain an OpenAI API key")

        parameter_name = os.getenv("OPENAI_API_KEY_SSM_PARAMETER_NAME", "").strip()
        if parameter_name:
            response = self.session.client("ssm").get_parameter(
                Name=parameter_name,
                WithDecryption=True,
            )
            return response["Parameter"]["Value"].strip()

        raise RuntimeError(
            "Missing OpenAI API key. Set OPENAI_API_KEY, OPENAI_API_KEY_SECRET_ARN, "
            "or OPENAI_API_KEY_SSM_PARAMETER_NAME."
        )

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate an embedding using the SageMaker endpoint.
        """
        response = self.sagemaker_runtime.invoke_endpoint(
            EndpointName=self.embedding_endpoint,
            ContentType="application/json",
            Body=json.dumps({"inputs": text}),
        )
        result = json.loads(response["Body"].read().decode("utf-8"))

        if isinstance(result, list) and result:
            first = result[0]
            if isinstance(first, list) and first:
                if isinstance(first[0], list):
                    return [float(value) for value in first[0]]
                return [float(value) for value in first]
            return [float(value) for value in result]

        raise ValueError("Unexpected embedding payload returned by SageMaker")

    def make_context(self, similars: List[str], prices: List[float]) -> str:
        """
        Create context that can be inserted into the prompt
        :param similars: similar products to the one being estimated
        :param prices: prices of the similar products
        :return: text to insert in the prompt that provides context
        """
        message = "To provide some context, here are some other items that might be similar to the item you need to estimate.\n\n"
        for similar, price in zip(similars, prices):
            message += f"Potentially related product:\n{similar}\nPrice is ${price:.2f}\n\n"
        return message

    def messages_for(
        self, description: str, similars: List[str], prices: List[float]
    ) -> List[Dict[str, str]]:
        """
        Create the message list to be included in a call to OpenAI
        With the system and user prompt
        :param description: a description of the product
        :param similars: similar products to this one
        :param prices: prices of similar products
        :return: the list of messages in the format expected by OpenAI
        """
        message = f"Estimate the price of this product. Respond with the price, no explanation\n\n{description}\n\n"
        message += self.make_context(similars, prices)
        return [{"role": "user", "content": message}]

    def find_similars(self, description: str):
        """
        Return a list of items similar to the given one by querying S3 Vectors.
        """
        self.log(
            "Frontier Agent is performing a RAG search of S3 Vectors to find 5 similar products"
        )
        vector = self.get_embedding(description)
        results = self.s3_vectors.query_vectors(
            vectorBucketName=self.vector_bucket,
            indexName=self.index_name,
            queryVector={"float32": vector},
            topK=self.top_k,
            returnMetadata=True,
            returnDistance=True,
        )

        documents = []
        prices = []
        for item in results.get("vectors", []):
            metadata = item.get("metadata") or {}
            text = metadata.get("text")
            price = metadata.get("price")
            if text and price is not None:
                documents.append(text)
                prices.append(float(price))

        self.log("Frontier Agent has found similar products")
        return documents, prices

    def get_price(self, s) -> float:
        """
        A utility that plucks a floating point number out of a string
        """
        s = s.replace("$", "").replace(",", "")
        match = re.search(r"[-+]?\d*\.\d+|\d+", s)
        return float(match.group()) if match else 0.0

    def price(self, description: str) -> float:
        """
        Make a call to OpenAI or DeepSeek to estimate the price of the described product,
        by looking up 5 similar products and including them in the prompt to give context
        :param description: a description of the product
        :return: an estimate of the price
        """
        started = time.perf_counter()
        documents, prices = self.find_similars(description)
        self.log(
            f"Frontier Agent is about to call {self.MODEL} with context including {len(documents)} similar products"
        )
        response = self.client.chat.completions.create(
            model=self.MODEL,
            messages=self.messages_for(description, documents, prices),
            seed=42,
            reasoning_effort="none",
        )
        reply = response.choices[0].message.content
        result = self.get_price(reply)
        logger.info(
            "frontier_price_success model=%s latency_ms=%.2f similars=%s price=%.2f",
            self.MODEL,
            (time.perf_counter() - started) * 1000,
            len(documents),
            result,
        )
        self.log(f"Frontier Agent completed - predicting ${result:.2f}")
        return result
