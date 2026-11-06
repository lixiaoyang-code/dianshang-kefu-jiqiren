FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 APP_MODE=demo
WORKDIR /app
COPY requirements.txt requirements-semantic.txt ./
RUN pip install --no-cache-dir -r requirements-semantic.txt

COPY app ./app
COPY static ./static
COPY data ./data
COPY scripts/download_semantic_model.py ./scripts/download_semantic_model.py
# Pinned ONNX model data only; no remote model repository code is executed.
# If Hugging Face is unavailable, build with --build-arg DOWNLOAD_SEMANTIC_MODEL=false
# and explicitly accept the semantic-model-missing status until a model is installed.
ARG DOWNLOAD_SEMANTIC_MODEL=true
RUN if [ "$DOWNLOAD_SEMANTIC_MODEL" = "true" ]; then python scripts/download_semantic_model.py; fi
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app \
    && mkdir -p /app/logs && chown -R app:app /app
USER 10001:10001
EXPOSE 8000
# Single worker is intentional: sessions, ownership and request budgets are in memory.
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
