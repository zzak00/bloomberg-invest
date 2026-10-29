# Bloomberg Invest

Knowledge-graph analyst tool for companies listed on the Casablanca Stock Exchange. It ingests AMMC filings, extracts facts with their sources, computes KPIs and Sharia screenings in Python, and answers questions with citations.

Product decisions live in the map issue (#1) and its closed tickets; one-way decisions are ADRs in `docs/adr/`.

The golden set in `golden/<document>/` is the ground truth for parser, extractor and answer tests: `golden.md` holds entities, facts and test questions, `figures.csv` the expected figures. The source PDFs are not committed; each `golden.md` gives the AMMC link and SHA256.

## Domain terms

- **Organisation**: any company, holding, state body, pension fund, insurer, bank, audit firm or aggregate; its `kind` says which, and one Organisation can play several roles. Avoid: institution, entity, company (unless it is one).
- **Aggregate**: an Organisation standing for a group of holders, such as "Free float" or "Treasury shares", one per company. Avoid: holder (for these).
- **Listing**: an Organisation's listing on an exchange, with ticker, ISIN, sector and compartment. A listed company is an Organisation with a Listing. Avoid: stock, security.
- **Fact**: one statement from one Passage, of one of nine kinds (shareholding, board seat, audit mandate, listing, financial figure, consolidation, dividend, auditor opinion, related-party agreement). Avoid: edge, relationship, claim.
- **Conflict**: two Facts with the same key (subject, kind, object, period or as-of date, basis) and different values. Both are kept. Same key and same value means they agree. Avoid: duplicate, error.
- **Period**: the span a flow figure covers, with real start and end dates (FY2025, H1 2026). Avoid: year.
- **As-of date**: the date a position holds on (a shareholding, a board seat, a balance-sheet item). Avoid: date, period.
- **Basis**: a financial figure's scope (consolidated or company-only) plus its accounting standard (IFRS, CGNC). Avoid: "consolidated" alone.
- **Line item**: the canonical name of a financial quantity (`revenue`, `total_assets`); the filing's own wording is its **label**. Avoid: metric, KPI.
- **KPI value**: a number computed in Python from Facts under a rule version; never extracted. Avoid: metric, score.
- **Screening**: a company's Sharia compliance status for one period, computed from KPI values under a standard and rule version. Avoid: rating.
- **Price**: a daily close for one security from the market data source, with date, currency, source and fetch time. A market data record, not a Fact; market cap is computed from it. Avoid: quote.
- **Chunk**: a retrieval unit inside one section; paragraphs are never split and a table is always one whole Chunk. Avoid: fragment, page.
- **Passage**: the exact span a Fact cites: a table cell, a text range or an image region. Avoid: chunk, source.
- **Run**: one execution of a processing step (parse, chunk, embed, extract, link, compute, answer), with its tool, model and configuration versions. Avoid: job, task.
- **Review**: a person's check of a Fact or figure: accepted or corrected. Avoid: validation, approval.
- **Superseded**: replaced by a newer Run's output; kept, never deleted. Avoid: deleted, overwritten.

## Maintaining this file

Keep this file for knowledge useful to almost every future agent session in this project.
Do not repeat what the codebase already shows; point to the authoritative file or command instead.
Prefer rewriting or pruning existing entries over appending new ones.
When updating this file, preserve this bar for all agents and keep entries concise.
