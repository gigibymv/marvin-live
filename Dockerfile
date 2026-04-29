FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY marvin/ ./marvin/
COPY marvin_ui/ ./marvin_ui/

RUN pip install --no-cache-dir -e ".[dev]"

RUN mkdir -p /data

ENV MARVIN_HOST=0.0.0.0
ENV MARVIN_DB_PATH=/data/marvin.db

EXPOSE 8095

CMD ["sh", "-c", "python -m uvicorn marvin_ui.server:app --host 0.0.0.0 --port ${PORT:-8095}"]
