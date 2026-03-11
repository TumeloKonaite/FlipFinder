import json
import logging
import os
import threading

from flask import Flask, Response, request

from inference import input_fn, model_fn, output_fn, predict_fn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

MODEL = None
MODEL_LOCK = threading.Lock()


@app.route("/ping", methods=["GET"])
def ping():
    return Response(response="OK", status=200)


@app.route("/invocations", methods=["POST"])
def invocations():
    try:
        content_type = request.content_type or "application/json"
        accept = request.headers.get("Accept", "application/json")

        parsed = input_fn(request.data, content_type)
        prediction = predict_fn(parsed, get_model())
        body, mime = output_fn(prediction, accept)

        return Response(response=body, status=200, mimetype=mime)
    except Exception as exc:
        logger.exception("Embedding inference failed")
        return Response(
            response=json.dumps({"error": str(exc)}),
            status=500,
            mimetype="application/json",
        )


def get_model():
    global MODEL

    if MODEL is not None:
        return MODEL

    with MODEL_LOCK:
        if MODEL is None:
            model_dir = os.environ.get("MODEL_DIR", "/opt/ml/model")
            logger.info("Lazy-loading sentence embedding model")
            MODEL = model_fn(model_dir)

    return MODEL
