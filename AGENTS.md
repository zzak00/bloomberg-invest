# Bloomberg Invest

Knowledge-graph analyst tool for companies listed on the Casablanca Stock Exchange. It ingests AMMC filings, extracts facts with their sources, computes KPIs and Sharia screenings in Python, and answers questions with citations.

Product decisions live in the map issue (#1) and its closed tickets; one-way decisions are ADRs in `docs/adr/`. The Neo4j graph shape is in `docs/graph-schema.md`.

The golden set in `golden/<document>/` is the ground truth for parser, extractor and answer tests: `golden.md` holds entities, facts and test questions, `figures.csv` the expected figures, `evidence.csv` where each test question's answer sits. The source PDFs are not committed; each `golden.md` gives the AMMC link and SHA256.

Run, test and develop: see `README.md`. To prove a change in the running app, follow `.claude/skills/verify-bloomberg-invest/SKILL.md`. Prototype a new pipeline step in `backend/notebooks/pipeline.ipynb` first, then move it into `bloomberg_invest`; commit notebooks without outputs.

## Backend layout

`backend/src/bloomberg_invest/` follows Architecture Patterns with Python (cosmicpython.com). Dependencies point inward: `entrypoints` -> `service_layer` -> `domain`.

- `domain/`: write models and their rules; imports no other layer.
- `service_layer/`: one module per use case (`ingest.py`); receives its adapters as arguments.
- `adapters/`: each port is a `typing.Protocol` (`Parser`, `GraphStore`, `Embedder`, `LLM`, `TokenCounter`) that real adapters inherit.
- `entrypoints/`: the CLI and the FastAPI app; they translate input and call a service.
- `views.py`: the read models the store returns and the API serves.
- `bootstrap.py`: the only place that names concrete adapters; picks each from its setting (`PARSER`, `EMBEDDER`, `LLM`).

Tests: `tests/unit/` (no Docker), `tests/integration/` (real Neo4j or Docling; one contract test per port, run on every implementation), `tests/e2e/` (through the API).

## Domain terms

- **Organisation**: any company, holding, state body, pension fund, insurer, bank, audit firm or aggregate; its `kind` says which, and one Organisation can play several roles. Avoid: institution, entity, company (unless it is one).
- **Issuer**: the role of the Organisation that files a Document (`ISSUED_BY`). Not a separate entity.
- **Aggregate**: an Organisation standing for a group of holders, such as "Free float" or "Treasury shares", one per company. Avoid: holder (for these).
- **Listing**: an Organisation's listing on an exchange, with ticker, ISIN, sector and compartment. A listed company is an Organisation with a Listing. Avoid: stock, security.
- **Fact**: one statement from one Passage, of one of nine kinds (shareholding, board seat, audit mandate, listing, financial figure, consolidation, dividend, auditor opinion, related-party agreement). Avoid: edge, relationship, claim.
- **Rejected figure**: a financial figure the LLM proposed whose value does not equal its Cell's number or appear in its quoted text. Kept with the reason, never a Fact (#19 R6). Avoid: invalid fact, error.
- **Conflict**: two Facts with the same key (subject, kind, object, period or as-of date, basis) and different values. Both are kept. Same key and same value means they agree. Avoid: duplicate, error.
- **Period**: the span a flow figure covers, with real start and end dates (FY2025, H1 2026). Avoid: year.
- **As-of date**: the date a position holds on (a shareholding, a board seat, a balance-sheet item). Avoid: date, period.
- **Basis**: a financial figure's scope (consolidated or company-only) plus its accounting standard (IFRS, CGNC). Avoid: "consolidated" alone.
- **Line item**: the canonical name of a financial quantity (`revenue`, `total_assets`); the filing's own wording is its **label**. Avoid: metric, KPI.
- **KPI value**: a number computed in Python from Facts under a rule version; never extracted. Avoid: metric, score.
- **Screening**: a company's Sharia compliance status for one period, computed from KPI values under a standard and rule version. Avoid: rating.
- **Price**: a daily close for one security from the market data source, with date, currency, source and fetch time. A market data record, not a Fact; market cap is computed from it. Avoid: quote.
- **Chunk**: the search and retrieval unit: a run of one section's headings and paragraphs, never splitting a paragraph, or a table, or one part of a long table cut between rows with its header repeated (ADR 0004). Avoid: fragment, page, paragraph (paragraphs exist only inside the chunker), passage (a Passage is what a Fact cites).
- **Passage**: the exact span a Fact cites: a table cell, a text range or an image region. In the graph, a second label on Cell and Span nodes, never a node of its own. Avoid: chunk, source.
- **Run**: one execution of a processing step (parse, chunk, embed, extract, link, compute, answer), with its tool, model and configuration versions. Avoid: job, task.
- **Review**: a person's check of a Fact or figure: accepted, corrected, or reopened to undo the one before. Only consolidated figures that feed a KPI or screen need one; the latest Review is the check in force. Avoid: validation, approval.
- **Superseded**: replaced by a newer Run's output; kept, never deleted. Avoid: deleted, overwritten.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
