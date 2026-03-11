import logging
from pathlib import Path
from threading import Lock

if __package__:
    from .deep_neural_network import DeepNeuralNetworkInference
else:
    from deep_neural_network import DeepNeuralNetworkInference

logger = logging.getLogger(__name__)

MODEL_PATH = Path(__file__).resolve().parent / "deep_neural_network_model.bin"
_MODEL = None
_MODEL_LOCK = Lock()


def get_inference_model() -> DeepNeuralNetworkInference:
    global _MODEL

    if _MODEL is not None:
        return _MODEL

    with _MODEL_LOCK:
        if _MODEL is None:
            logger.info("Loading in-process NN pricer from %s", MODEL_PATH)
            model = DeepNeuralNetworkInference()
            model.setup()
            model.load(str(MODEL_PATH))
            _MODEL = model

    return _MODEL


def price_description(description: str) -> float:
    return get_inference_model().inference(description)
