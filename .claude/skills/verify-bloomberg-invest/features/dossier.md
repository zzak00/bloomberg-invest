# Company dossier

A company's figures, extracted from its filings and checked against their cells (#22), and its filings.

## Sub-features

- Under the name, the company's listing and last close (#26): its ticker chip and sector beside the ISIN, then `CLOSE 91,70 MAD +2,1 %` (the change from the session before), `10/11/2026 · Bourse de Casablanca · raw close, not adjusted for dividends`, `History from …` and a three-year price line. A company with no listing shows none; a listing with no closes yet says to run `bloomberg prices backfill`.
- `FIGURES · n`, `FACTS · n` and `FILINGS · n` tabs; the dossier opens on FIGURES. FACTS is in [facts.md](facts.md).
- A basis switch, `CONSOLIDATED · IFRS` (default) or `COMPANY-ONLY · CGNC`, kept in the URL as `?basis=company-only`.
- One table per statement (income statement, balance sheet, cash flow, per share and dividends, company-reported measures): a row per line item, its breakdowns indented under it, a column per fiscal year, newest first. Values are as written in the filing, with the unit in its own column.
- Several passages stating the same value show "n sources"; a different value for the same line item and year shows under the first, marked `≠`.
- Each value opens the source viewer at `/documents/<id>?fact=<fact id>`, on the cell's page, the cell highlighted and the highlight bar reading `CELL Revenue · FY2025 36 681 MAD m p. 24` (`QUOTE` for a figure quoted from a paragraph).
- "No figures extracted yet" when the company's filings have none; an error state when the company is unknown.
- At 390 each line item becomes a block of `FY2025 ... value` lines.

## How to get to it (user POV)

On INDEX, click the company name in a row. Or open `/companies/<ISIN>`, for example http://localhost:8080/companies/MA0000011488.

## Driving it with Playwright

`getByRole("region", { name: "Income statement" })` is a statement; its values are links named `Revenue, FY2025: 36 681 MAD m, on page 24`. The basis buttons are `getByRole("button", { name: "COMPANY-ONLY · CGNC" })` with `aria-pressed`. In the viewer the cell is `.paper-sheet .mark` and the bar is `getByRole("status")`.

Proof: revenue FY2025 shows `36 681` under the income statement, and its link opens the page with one cell-sized mark.

The price block is `getByRole("group", { name: "Last close" })`; its line is `getByRole("img", { name: /^Closes from / })`.

## Gotchas

- The price block needs closes: `docker compose run --rm prices backfill` once (about 10 minutes), and `IAM = "MA0000011488"` in `backend/src/bloomberg_invest/config/listings/`.

- Figures need an extract Run: ingest runs it, which needs the Azure OpenAI secrets in `.env`. Without figures the dossier shows its empty state and the journey's AC4 checks fail.
- A filing ingested before #22 has no Cells: re-ingest it, then the figures can cite them.
