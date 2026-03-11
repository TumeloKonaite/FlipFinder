import json
import logging
import os
import time
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import boto3

if __package__:
    from .scanner_agent import ScannerAgent
else:
    from scanner_agent import ScannerAgent

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_AGENT = None
_TABLE = None


@dataclass
class _RememberedDeal:
    url: str


@dataclass
class _RememberedOpportunity:
    deal: _RememberedDeal


def _get_agent() -> ScannerAgent:
    global _AGENT
    if _AGENT is None:
        _AGENT = ScannerAgent()
    return _AGENT


def _get_table():
    global _TABLE
    if _TABLE is None:
        table_name = os.environ["SCANNER_MEMORY_TABLE"]
        _TABLE = boto3.resource("dynamodb").Table(table_name)
    return _TABLE


def _response(payload: dict[str, Any], status_code: int = 200) -> dict[str, Any]:
    return {
        "statusCode": status_code,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _decimalize(value: float) -> Decimal:
    return Decimal(str(round(value, 2)))


def _load_memory(limit: int) -> list[_RememberedOpportunity]:
    table = _get_table()
    scan_kwargs = {
        "ProjectionExpression": "#url",
        "ExpressionAttributeNames": {"#url": "url"},
        "Limit": limit,
    }
    response = table.scan(**scan_kwargs)
    items = response.get("Items", [])

    while "LastEvaluatedKey" in response and len(items) < limit:
        response = table.scan(
            **{
                **scan_kwargs,
                "Limit": max(limit - len(items), 1),
                "ExclusiveStartKey": response["LastEvaluatedKey"],
            }
        )
        items.extend(response.get("Items", []))

    urls = [item["url"] for item in items if item.get("url")]
    return [_RememberedOpportunity(deal=_RememberedDeal(url=url)) for url in urls]


def _persist_selection(selection) -> None:
    table = _get_table()
    scanned_at = int(time.time())

    with table.batch_writer(overwrite_by_pkeys=["url"]) as batch:
        for deal in selection.deals:
            batch.put_item(
                Item={
                    "url": deal.url,
                    "product_description": deal.product_description,
                    "price": _decimalize(deal.price),
                    "last_scanned_at": scanned_at,
                }
            )


def lambda_handler(event, context):
    started = time.perf_counter()
    memory_limit = int(os.getenv("SCANNER_MEMORY_MAX_ITEMS", "500"))

    try:
        memory = _load_memory(memory_limit)
        selection = _get_agent().scan(memory=memory)

        if selection:
            _persist_selection(selection)
            payload = {
                "message": "Scanner run completed",
                "deals_found": len(selection.deals),
                "deals": selection.model_dump(mode="json")["deals"],
            }
        else:
            payload = {
                "message": "Scanner run completed",
                "deals_found": 0,
                "deals": [],
            }

        logger.info(
            "scanner_lambda_success request_id=%s latency_ms=%.2f deals_found=%s",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
            payload["deals_found"],
        )
        return _response(payload)
    except Exception as exc:
        logger.exception("ScannerAgent execution failed")
        logger.error(
            "scanner_lambda_failure request_id=%s latency_ms=%.2f error=%s",
            getattr(context, "aws_request_id", "unknown"),
            (time.perf_counter() - started) * 1000,
            exc,
        )
        return _response({"error": str(exc)}, status_code=500)
