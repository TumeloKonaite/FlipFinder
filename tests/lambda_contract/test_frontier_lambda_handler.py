import json

from src.agents.FrontierAgent import lambda_handler as frontier_lambda


class _FakeContext:
    aws_request_id = "req-123"


class _FakeFrontierAgent:
    def price(self, description: str) -> float:
        assert description == "Nintendo Switch OLED"
        return 299.99


def test_frontier_lambda_returns_400_when_description_missing():
    response = frontier_lambda.lambda_handler({}, _FakeContext())
    body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert body["error"] == "Missing 'description'"


def test_frontier_lambda_accepts_api_gateway_body(monkeypatch):
    monkeypatch.setattr(frontier_lambda, "_get_agent", lambda: _FakeFrontierAgent())
    event = {"body": json.dumps({"description": "Nintendo Switch OLED"})}

    response = frontier_lambda.lambda_handler(event, _FakeContext())
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["price"] == 299.99
