import json

from src.agents.FrontierAgent.frontier_agent import FrontierAgent


class _FakeBody:
    def __init__(self, payload: str):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload.encode("utf-8")


class _FakeSageMakerRuntime:
    def __init__(self, payload: str):
        self._payload = payload

    def invoke_endpoint(self, **kwargs):
        return {"Body": _FakeBody(self._payload)}


def test_get_price_parses_currency_string():
    agent = FrontierAgent.__new__(FrontierAgent)

    assert agent.get_price("Estimated value is $1,249.99 now") == 1249.99
    assert agent.get_price("No number here") == 0.0


def test_get_embedding_parses_nested_payload_shape():
    nested_payload = json.dumps([[[0.1, 0.2, 0.3]]])
    agent = FrontierAgent.__new__(FrontierAgent)
    agent.embedding_endpoint = "fake-endpoint"
    agent.sagemaker_runtime = _FakeSageMakerRuntime(nested_payload)

    embedding = agent.get_embedding("wireless headphones")

    assert embedding == [0.1, 0.2, 0.3]
