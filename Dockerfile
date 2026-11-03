# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: builder
# ---------------------------------------------------------------------------
# Exports the locked production dependencies with Poetry and installs them
# into a clean virtualenv. Poetry and build tools stay in this stage; the
# runtime stage only copies /opt/venv.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Same Poetry major as .tool-versions: poetry.lock uses lock-version 2.1,
# which Poetry 1.x cannot read.
ENV POETRY_VERSION=2.2.1 \
    POETRY_NO_INTERACTION=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN pip install "poetry==${POETRY_VERSION}" poetry-plugin-export

COPY pyproject.toml poetry.lock ./

RUN poetry export --only main --format requirements.txt --output requirements.txt \
    && python -m venv /opt/venv \
    && /opt/venv/bin/pip install -r requirements.txt

# ---------------------------------------------------------------------------
# Stage 2: runtime
# ---------------------------------------------------------------------------
# Python + ffmpeg (probing, thumbnails, HLS). Runs as a non-root user whose
# uid matches the usual first user on a Linux host, so bind-mounted data
# directories stay writable.
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 homeflix

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=homeflix:homeflix src/ ./src/
COPY --chown=homeflix:homeflix migrations/ ./migrations/
COPY --chown=homeflix:homeflix alembic.ini ./
# Identity bootstrap (once per deployment), e.g.
#   docker compose exec backend python scripts/identity_create_admin.py
COPY --chown=homeflix:homeflix scripts/identity_*.py ./scripts/
COPY --chown=homeflix:homeflix docker/entrypoint.sh /entrypoint.sh

USER homeflix

# The project is not installed into the venv: PYTHONPATH lets scripts/ import src.
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8005

EXPOSE 8005

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --start-interval=2s --retries=3 \
  CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8005/health', timeout=3)"]

ENTRYPOINT ["/entrypoint.sh"]
