import json
import logging
import time

if __package__:
    from .frontier_agent import FrontierAgent
else:
    from frontier_agent import FrontierAgent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AGENT = None


def _get_agent() -> FrontierAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = FrontierAgent()
    return _AGENT


def _parse_event(event):
    if isinstance(event, dict) and "description" in event:
        return event["description"]

    if isinstance(event, dict) and "body" in event:
        body = event["body"]
        if isinstance(body, str):
            body = json.loads(body) if body else {}
        elif body is None:
            body = {}
        if isinstance(body, dict):
            return body.get("description", "")

    return ""


def _response(payload, status_code=200):
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def lambda_handler(event, context):
    started = time.perf_counter()
    try:
        description = _parse_event(event).strip()
        if not description:
            return _response({"error": "Missing 'description'"}, status_code=400)

        price = _get_agent().price(description)
        logger.info(
            "frontier_lambda_success request_id=%s latency_ms=%.2f",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
        )
        return _response({"price": price})
    except Exception as exc:
        logger.exception("FrontierAgent inference failed")
        logger.error(
            "frontier_lambda_failure request_id=%s latency_ms=%.2f error=%s",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
            exc,
        )
        return _response({"error": str(exc)}, status_code=500)
