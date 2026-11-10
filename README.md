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

Ingest then extracts the filing's financial figures (#22): each page with a table or a number goes to Azure OpenAI (`gpt-5.6-sol`), and Python keeps a figure only when its value equals the table cell or quoted text it cites. Set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` in `.env` first; ingest stops before parsing without them. To re-extract an ingested filing: `docker compose run --rm extract <document id>`. Its figures show on the company's dossier, opened from its name on INDEX.

CHECKS lists the consolidated figures that feed a KPI or Sharia screen (#23; the inputs are in `backend/src/bloomberg_invest/config/kpis/`), for a person to accept or correct before they count. Set `REVIEWER` in `.env` to the name checks should carry, then `docker compose up -d api`; until then CHECKS shows the queue but refuses checks. A re-extract keeps a check only on a figure read with the same value from the same cell; any other goes back to CHECKS.

`docker compose up --build` does not rebuild these tools, which share one image. After changing backend code, rebuild it before running them: `docker compose --profile tools build ingest`.

| Part | Where | Notes |
| --- | --- | --- |
| API | `backend/` (FastAPI, Python 3.12, uv) | `/api/docs` for the OpenAPI UI |
| Ingest | `backend/` with the `ingest` extra (Docling, the OpenAI client) | Kept out of the API image |
| Web app | `frontend/` (React, TypeScript, Vite) | `npm run dev` proxies `/api` to `localhost:8000` |
| Graph | Neo4j Community | Browser on http://localhost:7474 |

## Develop

```bash
docker compose --profile test up -d --wait neo4j-test   # throwaway database for the tests

cd backend
uv sync --locked --extra embed           # like the API image and CI
uv run pytest -m "not ingest"            # store, API, outline and embedder tests
uv run --extra ingest pytest -m ingest   # Docling parser, ingest and chunk tests
uv run --extra embed pytest -m embed     # the embedding model
uv run --extra ingest --env-file <secrets> pytest -m live   # the live Azure OpenAI model
uv run ruff check . && uv run ruff format --check .

cd ../frontend
npm ci
npm run gen:api       # after an API change: (cd ../backend && uv run python -m bloomberg_invest.entrypoints.api.openapi) > src/api/openapi.json first
npm run typecheck && npm run lint && npm run build
```

### The pipeline notebook

`backend/notebooks/pipeline.ipynb` runs the whole pipeline on one filing with the app's own functions: Docling's parse, blocks, chunks, embeddings and search, with the time each step takes, then writes an error-analysis page. It needs no running stack. The filing is the golden Maroc Telecom report unless `FILING` names another PDF in `data/inbox/`; only the golden one has ground truth, so only it is scored. New steps are tried there before they move into `bloomberg_invest`.

```bash
# once per clone: strip outputs on commit, with a pinned nbstripout that no checkout owns
git config filter.nbstripout.clean "uvx nbstripout==0.9.1"
git config filter.nbstripout.smudge cat
git config filter.nbstripout.required true
git config diff.ipynb.textconv "uvx nbstripout==0.9.1 -t"

cd backend
uv run --extra ingest --group notebook jupyter lab notebooks/pipeline.ipynb
FILING=AWB_RFA_2025.pdf uv run --extra ingest --group notebook jupyter lab notebooks/pipeline.ipynb
```

The first run on a filing parses it (a few minutes); the parse and the vectors are cached in `data/notebook/`.

Outputs are stripped on commit, and CI rejects a notebook with outputs: they show pages of the AMMC report.

The `golden` tests ingest the real report when it is at `data/inbox/Maroc_Telecom_RFA_2025.pdf`, and are skipped otherwise. The figures one (#22 AC5) replays the model's answers from `data/recordings/`, never committed; record them once, live, with `LLM_RECORD=1 uv run --extra ingest --env-file <secrets> pytest -m golden -s tests/integration/test_golden_figures.py`. No test calls a live model otherwise: the tests use a fake or a recording, and a recording holds the model's answers only.

To check a change in the browser at 1440, 1024 and 390, see `.claude/skills/verify-bloomberg-invest/SKILL.md`.
