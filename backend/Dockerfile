# One image definition, two targets: `api` (the embedder, no Docling) and `ingest` (the ingest
# extra, which includes the embedder).
FROM python:3.12-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS api
RUN uv sync --frozen --no-dev --extra embed --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra embed
EXPOSE 8000
CMD ["uvicorn", "bloomberg_invest.entrypoints.api.app:app", "--host", "0.0.0.0", "--port", "8000"]

FROM base AS ingest
# OpenCV, used by Docling's layout model, needs libgl1 and libglib2.0-0.
# Filings use Arial without embedding it. With no fonts, Docling draws every glyph
# as an empty box and its layout model misreads the page (tables become pictures or
# plain text). Liberation is metric-compatible with Arial, Helvetica, Times and Courier.
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 libglib2.0-0 fontconfig fonts-liberation \
    && rm -rf /var/lib/apt/lists/*
RUN fc-match Arial | grep -q '^LiberationSans' \
    || { echo "Arial does not resolve to Liberation Sans" >&2; exit 1; }
RUN uv sync --frozen --no-dev --extra ingest --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --extra ingest
ENTRYPOINT ["bloomberg", "ingest"]
