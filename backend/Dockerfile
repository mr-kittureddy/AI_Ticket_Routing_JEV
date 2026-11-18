# syntax=docker/dockerfile:1

# ---- build stage: compilers live here only, in case a dependency has no prebuilt wheel ----
FROM python:3.11-slim AS builder

ENV PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt


# ---- runtime stage ----
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    ANONYMIZED_TELEMETRY=False \
    DATABASE_URL="sqlite:////data/support_tickets.db" \
    CHROMA_PERSIST_DIR="/data/chroma"

# Non-root user. /data holds the SQLite file (standalone use) and the ChromaDB store; it is created and owned
# here so a named volume mounted at /data/chroma inherits the right ownership on first use.
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app --shell /usr/sbin/nologin app \
    && mkdir -p /app /data/chroma \
    && chown -R app:app /app /data

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=app:app alembic.ini ./
COPY --chown=app:app alembic ./alembic
COPY --chown=app:app app ./app

USER app

EXPOSE 8000

# python:slim has no curl, so the check uses the standard library. The long start period covers ChromaDB
# initialisation. /api/health answers 200 even when the database is degraded, so this only detects a dead process.
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"]

# Migrations first (idempotent), then the server. `exec` makes uvicorn PID 1 so it receives SIGTERM directly.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
