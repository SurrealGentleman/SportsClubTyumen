FROM python:3.12-slim AS builder

ENV POETRY_VERSION=2.4.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false

WORKDIR /app

RUN pip install --no-cache-dir "poetry==$POETRY_VERSION" \
    && python -m venv /opt/venv
ENV VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml poetry.lock ./

RUN poetry install --only main --no-root

FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv

COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY scripts/check_deployment.py ./scripts/check_deployment.py

USER 10001:10001

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
