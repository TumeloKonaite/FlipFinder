FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
ENV MODEL_DIR=/opt/ml/model
ENV PYTHONPATH=/opt/program

WORKDIR /opt/program

COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.5.1 && \
    pip install --no-cache-dir -r requirements.txt

COPY inference.py serve.py ./
COPY serve /usr/local/bin/serve
RUN chmod 755 /usr/local/bin/serve

EXPOSE 8080

ENTRYPOINT ["serve"]
