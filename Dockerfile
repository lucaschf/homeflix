# syntax=docker/dockerfile:1.7

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
# Installs Poetry, exports resolved production deps to requirements.txt,
# then builds a clean virtualenv with only those deps. The runtime stage
# copies /opt/venv from here — keeping Poetry and build tools out of the
# final image.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

ENV POETRY_VERSION=1.8.3 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry==${POETRY_VERSION}" poetry-plugin-export

COPY pyproject.toml poetry.lock ./

RUN poetry export --without dev --format requirements.txt --output requirements.txt

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
# Slim runtime with Python + ffmpeg + curl (for healthcheck). App code
# runs as a non-root user.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 homeflix

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv

COPY --chown=homeflix:homeflix src/ ./src/
COPY --chown=homeflix:homeflix migrations/ ./migrations/
COPY --chown=homeflix:homeflix alembic.ini ./
COPY --chown=homeflix:homeflix docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

USER homeflix

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8005

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD curl -fsS http://localhost:8005/health || exit 1

ENTRYPOINT ["/entrypoint.sh"]
