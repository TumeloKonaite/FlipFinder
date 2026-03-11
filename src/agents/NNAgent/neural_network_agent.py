import json
import os

import boto3

from src.agents.agent import Agent


class NeuralNetworkAgent(Agent):
    name = "Neural Network Agent"
    color = Agent.MAGENTA

    def __init__(self):
        """
        Initialize this object to invoke the deployed NN Lambda.
        Fall back to local inference only when no Lambda name is configured.
        """
        self.log("Neural Network Agent is initializing")
        self.lambda_name = os.getenv("NN_AGENT_LAMBDA_NAME", "").strip()
        self.region_name = (
            os.getenv("DEFAULT_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.lambda_client = boto3.client("lambda", region_name=self.region_name)
        self.log(
            "Neural Network Agent is ready"
            + (
                f" via Lambda {self.lambda_name}"
                if self.lambda_name
                else " with local fallback"
            )
        )

    def _invoke_lambda(self, description: str) -> float:
        response = self.lambda_client.invoke(
            FunctionName=self.lambda_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"description": description}).encode("utf-8"),
        )
        payload = json.loads(response["Payload"].read().decode("utf-8"))
        body = payload.get("body", payload)
        if isinstance(body, str):
            body = json.loads(body) if body else {}

        if payload.get("FunctionError"):
            raise RuntimeError(body.get("error", "NN Lambda invocation failed"))

        if payload.get("statusCode", 200) >= 400:
            raise RuntimeError(body.get("error", "NN Lambda returned an error"))

        return float(body["price"])

    def _price_locally(self, description: str) -> float:
        if __package__:
            from .inference_service import price_description
        else:
            from inference_service import price_description

        return float(price_description(description))

    def price(self, description: str) -> float:
        """
        Use the deployed NN Lambda to estimate the price of the described item.
        :param description: the product to be estimated
        :return: the price as a float
        """
        self.log("Neural Network Agent is starting a prediction")
        if self.lambda_name:
            result = self._invoke_lambda(description)
        else:
            result = self._price_locally(description)
        self.log(f"Neural Network Agent completed - predicting ${result:.2f}")
        return result
