---
name: verify-bloomberg-invest
description: Launch the Bloomberg Invest stack (Neo4j, FastAPI, React web app) with Docker Compose, ingest a filing, and drive the web UI with Playwright to capture screenshots at 1440, 1024 and 390. Use to prove a UI or API change works the way a user sees it, or when an acceptance criterion names a viewport.
---

# Verify Bloomberg Invest

The user-facing surface is the web app at http://localhost:8080 (nginx serving the React build and proxying `/api` to FastAPI). Data comes from AMMC PDFs ingested into Neo4j by a CLI. Commands run from the repository root.

## Launch

1. Docker: OrbStack provides `docker`; if it isn't on PATH, `export PATH=$HOME/.orbstack/bin:$PATH`. Start the app with `open -a OrbStack` if `docker info` fails.
2. `cp .env.example .env` once, then set a long `NEO4J_PASSWORD`. Start the stack:

   ```bash
   docker compose up -d --build --wait     # neo4j, api, web; --wait returns when all are healthy
   docker compose --profile tools build ingest   # ingest, chunk and embed share this image; `up --build` skips it
   ```

3. A journey needs at least one filing. The golden report (Maroc Telecom 2025, not committed: download it from the source URL in `golden/maroc-telecom-rfa-2025/golden.md` and check its SHA-256) goes in `data/inbox/`:

   ```bash
   docker compose run --rm ingest /data/inbox/Maroc_Telecom_RFA_2025.pdf \
     --issuer-isin MA0000011488 --issuer-name "Maroc Telecom" --doc-type annual_report \
     --fiscal-year 2025 --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
   ```

   Ingest also extracts figures with Azure OpenAI: set `AZURE_OPENAI_ENDPOINT` and `AZURE_OPENAI_API_KEY` in `.env` first. CHECKS records checks only with `REVIEWER` set in `.env`. Ready when it prints `Parsed 90 pages, ... sections (run ...); ...; extracted ... figures ...; document ...`. Expect about 10 minutes in the container (about 4 on the Mac host). The first run downloads Docling's models and the embedding model into the `models` volume. Re-ingesting the same PDF supersedes the previous parse; it does not duplicate the filing.

The Playwright browser comes from `frontend/node_modules`: run `npm ci` in `frontend/` and `npx playwright install chromium` there once.

## Doctor

```bash
.claude/skills/verify-bloomberg-invest/scripts/doctor.sh [base-url]
```

Read-only. Checks that docker is reachable, `.env` exists, neo4j, api and web are up, `/api/health` answers, and at least one filing is ingested. Run it first whenever anything looks off.

## Drive

```bash
node .claude/skills/verify-bloomberg-invest/scripts/journey.mjs [--base http://localhost:8080]
```

For each viewport (1440×900, 1024×768, 390×844) it opens INDEX, opens the first filing, pages to 2, jumps to NOTE 13 from the outline (page 54 in the golden report), searches "dividende proposé" (with "/", or the search icon at 390) and opens the first result, which must be page 10 with the dividend chunk highlighted (#21 AC3), opens Maroc Telecom's dossier from INDEX, switches its basis, opens revenue FY2025 with its cell highlighted (#22 AC4), then on CHECKS opens a correction, accepts revenue FY2025, sees "Checked by" in the source viewer and reopens it (#23), then visits MAP and KPIs. It checks what a user sees: rows, rendered page images, the page field, the highlighted section, the empty-state headings, no horizontal scroll and no console errors. It selects by role and accessible name (`list "Filings"`, `navigation "Sections"`, `button "NEXT →"`, `img "Page N of ..."`), not by coordinates.

The per-feature recipes are in [features/README.md](features/README.md). A change to a feature is proven only when its file's journey passes, not just the one convenient entry point.

## Evidence

Each run writes `verify-evidence/<timestamp>/` (gitignored): `<viewport>-<step>.png` per step and `journey.json` with every check and its result. The script exits 1 if any check fails. Look at the screenshots, not only the checks: compare them with the Claude Design prototype (https://claude.ai/artifact/AmgEVLBQWWRY2KM4jm1uFP, token sheet and source viewer) and fix anything that looks off.

Side effects worth checking alongside the UI: `data/documents/<sha256>.pdf` (the stored filing) and `data/pages/<sha256>/<n>.png` (pages rendered on first view).

## Cleanup

```bash
docker compose down            # stops the stack; keeps the neo4j-data and models volumes
docker compose down -v         # also deletes the graph and the downloaded models
```

Evidence in `verify-evidence/` survives both. Two stacks can't run side by side: ports 7474, 7687 and 8080 are fixed. Don't drive a stack someone else is using.

## Gotchas

- Docling's parse differs slightly between the Mac host and the Linux container. For example, the container reads "1.1 Chiffres consolidés en dirham" as text, not a heading, so the outline differs.
- The URL changes before React renders a new page. Wait for the target page's own image (`img "Page 54 of ..."`), not for "an image is loaded".
