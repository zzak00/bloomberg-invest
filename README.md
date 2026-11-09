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

Ingest also chunks the filing and embeds each Chunk for search (#21), with `Qwen3-Embedding-0.6B` (downloaded on first use, about 1.2 GB). To re-chunk an ingested filing from its saved parse, for example after changing `CHUNK_CAP` or `TABLE_CAP`: `docker compose run --rm chunk <document id>`, which embeds the new Chunks too. To re-embed only: `docker compose run --rm embed <document id>`.

Embedding runs on the CPU in the container, about 5 seconds per long Chunk, so a 90-page filing takes over 10 minutes there. On a Mac it uses the GPU and takes about 3 minutes: `cd backend && DATA_DIR=../data uv run --extra ingest --env-file ../.env bloomberg chunk <document id>` (or `ingest`, or `embed`).

`docker compose up --build` does not rebuild these three tools, which share one image. After changing backend code, rebuild it before running them: `docker compose --profile tools build ingest`.

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
uv run --extra ingest pytest -m ingest   # Docling parser, ingest and chunk tests
uv run --extra embed pytest -m embed     # the embedding model
uv run ruff check . && uv run ruff format --check .

cd ../frontend
npm ci
npm run gen:api       # after an API change: (cd ../backend && uv run python -m bloomberg_invest.entrypoints.api.openapi) > src/api/openapi.json first
npm run typecheck && npm run lint && npm run build
```

### The pipeline notebook

`backend/notebooks/pipeline.ipynb` runs each pipeline step on the golden filing with the app's own functions and shows the results. It starts from the app's own parse, so start the stack and ingest the golden PDF first. It shows the outline on the page, blocks, chunks, embeddings and search against the golden questions. New steps are tried there before they move into `bloomberg_invest`.

```bash
cd backend
uv run --group notebook nbstripout --install --attributes ../.gitattributes   # once per clone
uv run --extra ingest --group notebook jupyter lab notebooks/pipeline.ipynb
```

The notebook loads the repo's `.env` itself, so it also runs in a kernel VS Code starts.

Outputs are stripped on commit, and CI rejects a notebook with outputs: they show pages of the AMMC report.

The `golden` test ingests the real report when it is at `data/inbox/Maroc_Telecom_RFA_2025.pdf`, and is skipped otherwise.

To check a change in the browser at 1440, 1024 and 390, see `.claude/skills/verify-bloomberg-invest/SKILL.md`.
