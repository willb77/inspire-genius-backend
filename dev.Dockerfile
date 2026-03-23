FROM python:3.14.2-slim

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /app

RUN pip install --no-cache-dir "poetry>=2.0,<3.0"

RUN poetry --version

COPY pyproject.toml poetry.lock ./

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    build-essential \
    poppler-utils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

RUN poetry config virtualenvs.create false \
    && poetry install --only main --no-interaction --no-ansi

COPY prism_inspire/ ./prism_inspire/
COPY ai/ ./ai/
COPY users/ ./users/
COPY alembic.ini .

RUN chown -R appuser:appuser /app

USER appuser

CMD ["/bin/sh", "-c", "uvicorn prism_inspire.main:app --host 0.0.0.0 --port 8000 --reload"]
