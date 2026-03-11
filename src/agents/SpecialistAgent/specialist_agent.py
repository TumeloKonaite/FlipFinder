import json
import os

import boto3

from src.agents.agent import Agent


class SpecialistAgent(Agent):
    name = "Specialist Agent"
    color = Agent.RED

    def __init__(self):
        self.log("Specialist Agent is initializing")
        region = os.getenv("AWS_REGION", os.getenv("DEFAULT_AWS_REGION", "us-east-1"))
        self.runtime = boto3.client("sagemaker-runtime", region_name=region)
        self.endpoint_name = os.environ["SAGEMAKER_ENDPOINT_NAME"]
        self.log(f"Using SageMaker endpoint: {self.endpoint_name}")

    def price(self, description: str) -> float:
        self.log("Specialist Agent is invoking SageMaker endpoint")

        response = self.runtime.invoke_endpoint(
            EndpointName=self.endpoint_name,
            ContentType="application/json",
            Accept="application/json",
            Body=json.dumps({"description": description}),
        )

        payload = json.loads(response["Body"].read().decode("utf-8"))
        result = float(payload.get("price", 0.0))

        self.log(f"Specialist Agent completed - predicting ${result:.2f}")
        return result
