# Filings index

Every ingested filing, with its company, document type, fiscal year, page count and ingest time.

## Sub-features

- One row per Document; the row opens the source viewer, and the company name opens its dossier.
- Loading skeleton, "No filings yet" when the graph is empty, an error state when the API fails.
- At 390 the table stacks into one block per filing.

## How to get to it (user POV)

Open http://localhost:8080 (redirects to `/index`) or click INDEX in the top navigation.

## Driving it with Playwright

`page.getByRole("list", { name: "Filings" }).getByRole("listitem")` gives the rows; in a row, the link named after the document type opens the filing and the one named after the company opens its dossier; `getByRole("link", { name: "INDEX" })` has `aria-current="page"`. Proof: at least one row, and the screenshot shows company, ISIN, "Annual financial report", `FY2025`, `90 p.` and the ingest time.

## Gotchas

- The empty state needs an empty graph: `docker compose down -v` deletes it.
