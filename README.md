# Bloomberg Invest

A knowledge-graph analyst tool for companies listed on the Casablanca Stock Exchange (working name). It ingests AMMC filings into Neo4j and shows them in a web app. The product spec is #19; decisions are on the map in #1 and in `docs/adr/`.

## Run it

Needs Docker with Compose (OrbStack on macOS).

```bash
cp .env.example .env                 # then set a long NEO4J_PASSWORD
docker compose up -d --build --wait  # Neo4j, API and web app
open http://localhost:8080
```

Ingest a filing. PDFs go under `data/`, which is not committed, because AMMC documents are not redistributed:

```bash
docker compose run --rm ingest /data/inbox/Maroc_Telecom_RFA_2025.pdf \
  --issuer-isin MA0000011488 --issuer-name "Maroc Telecom" --doc-type annual_report \
  --fiscal-year 2025 --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
```

The first ingest downloads Docling's models (kept in a volume). A 90-page report takes about 10 minutes in the container. On the host it takes about 4: `cd backend && NEO4J_PASSWORD=... DATA_DIR=../data uv run --extra ingest bloomberg ingest ...`.

| Part | Where | Notes |
| --- | --- | --- |
| API | `backend/` (FastAPI, Python 3.12, uv) | `/api/docs` for the OpenAPI UI |
| Ingest | `backend/` with the `ingest` extra (Docling) | Kept out of the API image |
| Web app | `frontend/` (React, TypeScript, Vite) | `npm run dev` proxies `/api` to `localhost:8000` |
| Graph | Neo4j Community | Browser on http://localhost:7474 |

## Develop

```bash
docker compose --profile test up -d --wait neo4j-test   # throwaway database for the tests

cd backend
uv sync --locked                         # API only, like the API image
uv run pytest -m "not ingest"            # store, API and outline tests
uv run --extra ingest pytest -m ingest   # Docling parser and ingest tests
uv run ruff check . && uv run ruff format --check .

cd ../frontend
npm ci
npm run gen:api       # after an API change: (cd ../backend && uv run python -m bloomberg_invest.entrypoints.api.openapi) > src/api/openapi.json first
npm run typecheck && npm run lint && npm run build
```

The `golden` test ingests the real report when it is at `data/inbox/Maroc_Telecom_RFA_2025.pdf`, and is skipped otherwise.

To check a change in the browser at 1440, 1024 and 390, see `.claude/skills/verify-bloomberg-invest/SKILL.md`.
