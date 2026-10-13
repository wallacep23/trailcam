# API and worker image (one image, two commands). Build context: repository root.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH

# pg_dump 16 (for pre-migration backups, NFR-4) must match the server's major version.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl postgresql-common \
 && /usr/share/postgresql-common/pgdg/apt.postgresql.org.sh -y \
 && apt-get install -y --no-install-recommends postgresql-client-16 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.7.2 /uv /uvx /bin/

WORKDIR /app/backend
# Dependencies first so code edits don't invalidate the layer.
COPY backend/pyproject.toml backend/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev --no-install-project

COPY backend/ ./
COPY scripts/ /app/scripts/
COPY models/ /app/models/
RUN --mount=type=cache,target=/root/.cache/uv uv sync --frozen --no-dev

ENV TRAILCAM_MODELS_REGISTRY=/app/models/registry.yaml
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
  CMD curl -fsS http://localhost:8000/api/v1/health > /dev/null || exit 1
CMD ["uvicorn", "--factory", "trailcam.api.main:app_factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
