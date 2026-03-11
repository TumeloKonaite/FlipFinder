import json
import importlib
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import boto3

from src.agents.agent import Agent
from src.agents.EnsembleAgent.preprocessor import Preprocessor

logger = logging.getLogger(__name__)


class EnsembleAgent(Agent):
    name = "Ensemble Agent"
    color = Agent.YELLOW

    AGENT_CONFIG = {
        "frontier": {
            "default_weight": 0.8,
            "weight_env": "ENSEMBLE_WEIGHT_FRONTIER",
            "lambda_env": "FRONTIER_AGENT_LAMBDA_NAME",
            "factory_path": "src.agents.FrontierAgent.frontier_agent:FrontierAgent",
        },
        "specialist": {
            "default_weight": 0.1,
            "weight_env": "ENSEMBLE_WEIGHT_SPECIALIST",
            "lambda_env": "SPECIALIST_AGENT_LAMBDA_NAME",
            "factory_path": "src.agents.SpecialistAgent.specialist_agent:SpecialistAgent",
        },
        "neural_network": {
            "default_weight": 0.1,
            "weight_env": "ENSEMBLE_WEIGHT_NN",
            "lambda_env": "NN_AGENT_LAMBDA_NAME",
            "factory_path": "src.agents.NNAgent.neural_network_agent:NeuralNetworkAgent",
        },
    }

    def __init__(self):
        self.log("Initializing Ensemble Agent")
        self.preprocessor = Preprocessor()
        self.lambda_client = boto3.client(
            "lambda",
            region_name=(
                os.getenv("DEFAULT_AWS_REGION")
                or os.getenv("AWS_REGION")
                or os.getenv("AWS_DEFAULT_REGION")
                or "us-east-1"
            ),
        )
        self.require_remote_agents = os.getenv(
            "ENSEMBLE_REQUIRE_REMOTE_AGENTS",
            "false",
        ).lower() in {"1", "true", "yes", "on"}
        self.weights = self._load_weights()
        self.lambda_targets = {
            name: os.getenv(config["lambda_env"], "").strip()
            for name, config in self.AGENT_CONFIG.items()
        }
        self._validate_runtime_configuration()
        self.local_agents = {
            name: self._build_local_agent(config["factory_path"])
            for name, config in self.AGENT_CONFIG.items()
            if not self.lambda_targets[name]
        }
        self.log("Ensemble Agent is ready")

    def _load_weights(self) -> dict[str, float]:
        weights = {}
        for name, config in self.AGENT_CONFIG.items():
            value = os.getenv(config["weight_env"])
            weights[name] = float(value) if value else config["default_weight"]
        return weights

    def _build_local_agent(self, factory_path: str) -> Any:
        module_name, class_name = factory_path.split(":")
        module = importlib.import_module(module_name)
        factory = getattr(module, class_name)
        return factory()

    def _validate_runtime_configuration(self) -> None:
        if not self.require_remote_agents:
            return

        missing = [
            name
            for name, target in self.lambda_targets.items()
            if not target
        ]
        if missing:
            names = ", ".join(sorted(missing))
            raise RuntimeError(
                "AWS-only ensemble mode requires Lambda targets for: "
                f"{names}"
            )

    def _parse_lambda_body(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = payload.get("body", payload)
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        if not isinstance(body, dict):
            raise ValueError("Lambda returned a non-JSON response body")
        return body

    def _log_event(self, event_name: str, **fields: Any) -> None:
        logger.info(
            json.dumps(
                {
                    "event": event_name,
                    **fields,
                },
                sort_keys=True,
                default=str,
            )
        )

    def _invoke_lambda(self, function_name: str, description: str) -> float:
        response = self.lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps({"description": description}).encode("utf-8"),
        )
        payload = json.loads(response["Payload"].read().decode("utf-8"))
        body = self._parse_lambda_body(payload)

        if payload.get("FunctionError"):
            raise RuntimeError(body.get("error", "Downstream Lambda invocation failed"))

        if payload.get("statusCode", 200) >= 400:
            raise RuntimeError(body.get("error", "Downstream Lambda returned an error"))

        return float(body["price"])

    def _call_agent(self, agent_name: str, description: str) -> dict[str, Any]:
        started = time.perf_counter()
        target = self.lambda_targets.get(agent_name)
        target_type = "lambda" if target else "local"
        try:
            if target:
                self.log(f"Invoking {agent_name} Lambda {target}")
                price = self._invoke_lambda(target, description)
            else:
                price = self.local_agents[agent_name].price(description)
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self._log_event(
                "agent_success",
                agent=agent_name,
                latency_ms=latency_ms,
                price=float(price),
                target=target or agent_name,
                target_type=target_type,
            )
            return {
                "status": "ok",
                "price": float(price),
                "latency_ms": latency_ms,
                "target_type": target_type,
            }
        except Exception as exc:
            latency_ms = round((time.perf_counter() - started) * 1000, 2)
            self.log(f"{agent_name} failed: {exc}")
            self._log_event(
                "agent_failure",
                agent=agent_name,
                latency_ms=latency_ms,
                error=str(exc),
                target=target or agent_name,
                target_type=target_type,
            )
            return {
                "status": "error",
                "error": str(exc),
                "latency_ms": latency_ms,
                "target_type": target_type,
            }

    def _combine(self, results: dict[str, dict[str, Any]]) -> float:
        successful = {
            name: result["price"]
            for name, result in results.items()
            if result.get("status") == "ok"
        }
        if not successful:
            raise RuntimeError("All ensemble agents failed")

        total_weight = sum(self.weights[name] for name in successful)
        if total_weight <= 0:
            raise RuntimeError("Ensemble weights must sum to a positive value")

        return sum(
            price * (self.weights[name] / total_weight)
            for name, price in successful.items()
        )

    def quote(self, description: str) -> dict[str, Any]:
        total_started = time.perf_counter()
        self.log("Running Ensemble Agent - preprocessing text")
        preprocess_started = time.perf_counter()
        rewrite = self.preprocessor.preprocess(description)
        preprocess_latency_ms = round(
            (time.perf_counter() - preprocess_started) * 1000,
            2,
        )
        self.log(f"Pre-processed text using {self.preprocessor.model_name}")
        self._log_event(
            "preprocessor_complete",
            latency_ms=preprocess_latency_ms,
            model=self.preprocessor.model_name,
        )

        results: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=3) as executor:
            future_to_agent = {
                executor.submit(self._call_agent, agent_name, rewrite): agent_name
                for agent_name in self.AGENT_CONFIG
            }
            for future in as_completed(future_to_agent):
                agent_name = future_to_agent[future]
                results[agent_name] = future.result()

        combined = self._combine(results)
        total_latency_ms = round((time.perf_counter() - total_started) * 1000, 2)
        self._log_event(
            "ensemble_complete",
            latency_ms=total_latency_ms,
            price=combined,
            successful_agents=[
                name for name, result in results.items() if result.get("status") == "ok"
            ],
        )
        self.log(f"Ensemble Agent complete - returning ${combined:.2f}")
        return {
            "price": combined,
            "rewrite": rewrite,
            "preprocessor_latency_ms": preprocess_latency_ms,
            "latency_ms": total_latency_ms,
            "components": results,
            "weights": self.weights,
        }

    def price(self, description: str) -> float:
        return float(self.quote(description)["price"])
