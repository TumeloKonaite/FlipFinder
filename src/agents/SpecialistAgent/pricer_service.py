import json
import os
import time

import boto3

runtime = boto3.client(
    "sagemaker-runtime",
    region_name=os.getenv("AWS_REGION", os.getenv("DEFAULT_AWS_REGION", "us-east-1")),
)
ENDPOINT_NAME = os.environ["SAGEMAKER_ENDPOINT_NAME"]


def lambda_handler(event, context):
    started = time.perf_counter()
    try:
        if "description" in event:
            body = event
        else:
            body = event.get("body", "{}")
            if isinstance(body, str):
                body = json.loads(body)
            elif body is None:
                body = {}

        description = body.get("description", "").strip()
        if not description:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"error": "Missing 'description'"}),
            }

        response = runtime.invoke_endpoint(
            EndpointName=ENDPOINT_NAME,
            ContentType="application/json",
            Accept="application/json",
            Body=json.dumps({"description": description}),
        )

        result = json.loads(response["Body"].read().decode("utf-8"))
        print(
            f"specialist_lambda_success request_id={getattr(context, 'aws_request_id', 'unknown')} "
            f"latency_ms={(time.perf_counter() - started) * 1000:.2f}"
        )

        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(result),
        }

    except Exception as exc:
        print(
            f"specialist_lambda_failure request_id={getattr(context, 'aws_request_id', 'unknown')} "
            f"latency_ms={(time.perf_counter() - started) * 1000:.2f} error={exc}"
        )
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps({"error": str(exc)}),
        }
