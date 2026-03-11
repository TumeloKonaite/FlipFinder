import json
import logging
import time

from src.agents.planning_agent import PlanningAgent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AGENT = None


def _get_agent() -> PlanningAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = PlanningAgent()
    return _AGENT


def _parse_event(event):
    if isinstance(event, dict) and "memory" in event:
        memory = event["memory"]
        return memory if isinstance(memory, list) else []

    if isinstance(event, dict) and "body" in event:
        body = event["body"]
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        elif body is None:
            body = {}
        if isinstance(body, dict):
            memory = body.get("memory", [])
            return memory if isinstance(memory, list) else []

    return []


def _response(payload, status_code=200):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    started = time.perf_counter()
    try:
        memory = _parse_event(event)
        result = _get_agent().plan(memory=memory)
        payload = {
            "opportunity": result.model_dump(mode="json") if result else None,
            "notified": bool(result),
        }
        logger.info(
            "planning_lambda_success request_id=%s latency_ms=%.2f notified=%s",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
            payload["notified"],
        )
        return _response(payload)
    except Exception as exc:
        logger.exception("PlanningAgent orchestration failed")
        logger.error(
            "planning_lambda_failure request_id=%s latency_ms=%.2f error=%s",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
            exc,
        )
        return _response({"error": str(exc)}, status_code=500)
