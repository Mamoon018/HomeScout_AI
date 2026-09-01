# syntax=docker/dockerfile:1

# --- Stage 1: builder — compile/install Python deps ---
FROM python:3.13-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Native wheels for uvicorn[standard] / cryptography
RUN apt-get update \
 && apt-get install -y --no-install-recommends gcc python3-dev \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Cache-friendly: dependency file alone first
COPY requirements.txt .

RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt


# --- Stage 2: runtime — minimal runnable image ---
FROM python:3.13-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app"

WORKDIR /app

# Non-root execution
RUN groupadd --system app \
 && useradd --system --gid app --home-dir /app --no-create-home app

# Reuse installed deps from builder (no compilers in final image)
COPY --from=builder /opt/venv /opt/venv

# Application source only (not tests/, certs/, README)
COPY src ./src

RUN chown -R app:app /app

USER app

EXPOSE 8000

# Production: HTTP inside container; TLS terminates upstream
# Matches import path used locally: src.app.main:app
CMD ["uvicorn", "src.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
