import json

from src.agents.EnsembleAgent import lambda_handler as ensemble_lambda


class _FakeContext:
    aws_request_id = "req-456"


class _FakeEnsembleAgent:
    def quote(self, description: str) -> dict:
        assert description == "Apple Watch Series 9 GPS 45mm"
        return {
            "price": 349.0,
            "rewrite": "Title: Apple Watch Series 9 GPS 45mm\nCategory: Wearables\nBrand: Apple\nDescription: Smart watch with health and fitness tracking.\nDetails: 45mm GPS model with advanced sensors.",
            "preprocessor_latency_ms": 10.0,
            "latency_ms": 42.0,
            "components": {
                "frontier": {"status": "ok", "price": 350.0},
                "specialist": {"status": "ok", "price": 340.0},
                "neural_network": {"status": "ok", "price": 355.0},
            },
            "weights": {
                "frontier": 0.8,
                "specialist": 0.1,
                "neural_network": 0.1,
            },
        }


def test_ensemble_lambda_returns_400_when_description_missing():
    response = ensemble_lambda.lambda_handler({}, _FakeContext())
    body = json.loads(response["body"])

    assert response["statusCode"] == 400
    assert body["error"] == "Missing 'description'"


def test_ensemble_lambda_returns_quote_payload(monkeypatch):
    monkeypatch.setattr(ensemble_lambda, "_get_agent", lambda: _FakeEnsembleAgent())
    event = {"body": json.dumps({"description": "Apple Watch Series 9 GPS 45mm"})}

    response = ensemble_lambda.lambda_handler(event, _FakeContext())
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["price"] == 349.0
    assert "components" in body
    assert set(body["weights"]) == {"frontier", "specialist", "neural_network"}
