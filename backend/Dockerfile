# One image definition, two targets: `api` (no Docling) and `ingest` (with the ingest extra).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS api
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
EXPOSE 8000
CMD ["uvicorn", "bloomberg_invest.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS ingest
# OpenCV, used by Docling's layout model, needs these system libraries.
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
RUN uv sync --frozen --no-dev --extra ingest --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra ingest
ENTRYPOINT ["bloomberg", "ingest"]
