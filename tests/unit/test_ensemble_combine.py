import pytest

from src.agents.EnsembleAgent.ensemble_agent import EnsembleAgent


def test_combine_uses_only_successful_agents_and_renormalizes_weights():
    agent = EnsembleAgent.__new__(EnsembleAgent)
    agent.weights = {
        "frontier": 0.8,
        "specialist": 0.1,
        "neural_network": 0.1,
    }
    results = {
        "frontier": {"status": "ok", "price": 100.0},
        "specialist": {"status": "error", "error": "timeout"},
        "neural_network": {"status": "ok", "price": 200.0},
    }

    combined = agent._combine(results)

    # (100*0.8 + 200*0.1) / (0.8 + 0.1)
    assert combined == pytest.approx(111.1111, abs=1e-3)


def test_combine_raises_when_all_agents_fail():
    agent = EnsembleAgent.__new__(EnsembleAgent)
    agent.weights = {
        "frontier": 0.8,
        "specialist": 0.1,
        "neural_network": 0.1,
    }
    results = {
        "frontier": {"status": "error"},
        "specialist": {"status": "error"},
        "neural_network": {"status": "error"},
    }

    with pytest.raises(RuntimeError, match="All ensemble agents failed"):
        agent._combine(results)


def test_combine_raises_when_successful_weights_sum_to_zero():
    agent = EnsembleAgent.__new__(EnsembleAgent)
    agent.weights = {
        "frontier": 0.0,
        "specialist": 0.0,
        "neural_network": 0.0,
    }
    results = {
        "frontier": {"status": "ok", "price": 120.0},
    }

    with pytest.raises(RuntimeError, match="weights must sum to a positive value"):
        agent._combine(results)
