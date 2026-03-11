import importlib
import json
import os
from typing import Any, Optional

import boto3

from src.agents.agent import Agent
from src.agents.MessangingAgent.messaging_agent import MessagingAgent
from src.agents.ScannerAgent.deals import Deal, DealSelection, Opportunity


class PlanningAgent(Agent):
    name = "Planning Agent"
    color = Agent.GREEN
    DEAL_THRESHOLD = 50

    def __init__(self):
        """
        Create instances of the agents that this planner coordinates across.
        Scanner and Ensemble can run remotely via Lambda when configured.
        """
        self.log("Planning Agent is initializing")
        region = (
            os.getenv("DEFAULT_AWS_REGION")
            or os.getenv("AWS_REGION")
            or os.getenv("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        self.lambda_client = boto3.client("lambda", region_name=region)
        self.scanner_lambda_name = os.getenv("SCANNER_AGENT_LAMBDA_NAME", "").strip()
        self.ensemble_lambda_name = os.getenv("ENSEMBLE_AGENT_LAMBDA_NAME", "").strip()
        self.scanner = None if self.scanner_lambda_name else self._build_local_agent(
            "src.agents.ScannerAgent.scanner_agent:ScannerAgent"
        )
        self.ensemble = None if self.ensemble_lambda_name else self._build_local_agent(
            "src.agents.EnsembleAgent.ensemble_agent:EnsembleAgent"
        )
        self.messenger = MessagingAgent()
        self.log("Planning Agent is ready")

    def _build_local_agent(self, factory_path: str):
        module_name, class_name = factory_path.split(":")
        module = importlib.import_module(module_name)
        factory = getattr(module, class_name)
        return factory()

    def _parse_lambda_body(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = payload.get("body", payload)
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        if not isinstance(body, dict):
            raise ValueError("Lambda returned a non-JSON response body")
        return body

    def _invoke_lambda(self, function_name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self.lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload or {}).encode("utf-8"),
        )
        raw_payload = json.loads(response["Payload"].read().decode("utf-8"))
        body = self._parse_lambda_body(raw_payload)

        if response.get("FunctionError") or raw_payload.get("FunctionError"):
            raise RuntimeError(body.get("error", f"{function_name} invocation failed"))

        if raw_payload.get("statusCode", 200) >= 400:
            raise RuntimeError(body.get("error", f"{function_name} returned an error"))

        return body

    def _scan(self, memory: list[str]) -> Optional[DealSelection]:
        if self.scanner_lambda_name:
            self.log(f"Planning Agent is invoking Scanner Lambda {self.scanner_lambda_name}")
            body = self._invoke_lambda(
                self.scanner_lambda_name,
                {"memory": memory},
            )
            deals = body.get("deals", [])
            return DealSelection(deals=deals) if deals else None

        return self.scanner.scan(memory=memory) if self.scanner else None

    def _estimate_price(self, description: str) -> float:
        if self.ensemble_lambda_name:
            self.log(f"Planning Agent is invoking Ensemble Lambda {self.ensemble_lambda_name}")
            body = self._invoke_lambda(
                self.ensemble_lambda_name,
                {"description": description},
            )
            return float(body["price"])

        if not self.ensemble:
            raise RuntimeError("No EnsembleAgent runtime is configured")
        return float(self.ensemble.price(description))

    def run(self, deal: Deal) -> Opportunity:
        """
        Run the workflow for a particular deal.
        """
        self.log("Planning Agent is pricing up a potential deal")
        estimate = self._estimate_price(deal.product_description)
        discount = estimate - deal.price
        self.log(f"Planning Agent has processed a deal with discount ${discount:.2f}")
        return Opportunity(deal=deal, estimate=estimate, discount=discount)

    def plan(self, memory: Optional[list[str]] = None) -> Optional[Opportunity]:
        """
        Run the full workflow:
        1. Use the ScannerAgent to find deals from RSS feeds
        2. Use the EnsembleAgent to estimate them
        3. Use the MessagingAgent to send a notification of deals
        """
        self.log("Planning Agent is kicking off a run")
        memory = memory or []
        selection = self._scan(memory=memory)
        if selection and selection.deals:
            opportunities = [self.run(deal) for deal in selection.deals[:5]]
            opportunities.sort(key=lambda opp: opp.discount, reverse=True)
            best = opportunities[0]
            self.log(
                f"Planning Agent has identified the best deal has discount ${best.discount:.2f}"
            )
            if best.discount > self.DEAL_THRESHOLD:
                self.messenger.alert(best)
            self.log("Planning Agent has completed a run")
            return best if best.discount > self.DEAL_THRESHOLD else None
        return None
