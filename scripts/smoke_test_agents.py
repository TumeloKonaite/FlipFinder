#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from typing import Any

import boto3


DEFAULT_DESCRIPTION = (
    "Apple iPhone 13 Pro Max 256GB unlocked smartphone in excellent condition"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Invoke the pricing agent Lambdas end to end and print a JSON summary."
    )
    parser.add_argument("--region", default=os.getenv("AWS_REGION", "us-east-1"))
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    parser.add_argument("--frontier", default=os.getenv("FRONTIER_AGENT_LAMBDA_NAME", "pricing-frontier-agent-pricer"))
    parser.add_argument("--specialist", default=os.getenv("SPECIALIST_AGENT_LAMBDA_NAME", "pricing-specialist-wrapper"))
    parser.add_argument("--nn", default=os.getenv("NN_AGENT_LAMBDA_NAME", "pricing-nn-agent-pricer"))
    parser.add_argument("--ensemble", default=os.getenv("ENSEMBLE_AGENT_LAMBDA_NAME", "pricing-ensemble-orchestrator"))
    return parser.parse_args()


def parse_payload(raw_payload: dict[str, Any]) -> Any:
    body = raw_payload.get("body", raw_payload)
    if isinstance(body, str):
        body = json.loads(body) if body else {}
    return body


def invoke_lambda(client: Any, function_name: str, description: str) -> dict[str, Any]:
    started = time.perf_counter()
    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"description": description}).encode("utf-8"),
    )
    payload = json.loads(response["Payload"].read().decode("utf-8"))
    latency_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "status_code": response.get("StatusCode"),
        "function_error": response.get("FunctionError"),
        "latency_ms": latency_ms,
        "payload": payload,
        "body": parse_payload(payload),
    }


def main() -> int:
    args = parse_args()
    client = boto3.client("lambda", region_name=args.region)
    functions = {
        "frontier": args.frontier,
        "specialist": args.specialist,
        "neural_network": args.nn,
        "ensemble": args.ensemble,
    }

    summary: dict[str, Any] = {
        "region": args.region,
        "description": args.description,
        "results": {},
    }

    exit_code = 0
    for agent_name, function_name in functions.items():
        result = invoke_lambda(client, function_name, args.description)
        summary["results"][agent_name] = {
            "function_name": function_name,
            "status_code": result["status_code"],
            "function_error": result["function_error"],
            "latency_ms": result["latency_ms"],
            "body": result["body"],
        }
        if result["function_error"] or result["payload"].get("statusCode", 200) >= 400:
            exit_code = 1

    print(json.dumps(summary, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
