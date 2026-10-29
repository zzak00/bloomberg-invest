# Parser bake-off (#10)

Throwaway prototype: run Docling and Azure Document Intelligence (prebuilt-layout) on the Maroc Telecom 2025 annual report, and score each against golden v0 (`golden/maroc-telecom-rfa-2025/figures.csv`).

```sh
uv sync
uv run bakeoff fetch                    # download the PDF into data/ and check its SHA256
uv run bakeoff parse docling            # local, no credentials
uv run --env-file ~/.config/bloomberg-invest/bakeoff.env bakeoff parse azure
uv run bakeoff score                    # writes data/report.md
```

The Azure step reads `AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT` and `AZURE_DOCUMENT_INTELLIGENCE_KEY` from an env file kept outside the repository. The free F0 tier analyses only the first 2 pages of a document, so the full report needs the S0 tier.

`data/` (PDF, raw parser output, normalised output, report) is ignored by Git. The PDF is not redistributed.

## Scoring

For each golden figure, the scorer looks for a table cell with the same number on the cited page, then checks its row and column labels. Outcomes: `exact`, `row_only`, `value_only`, `in_text`, `missing`. A miss is not automatically a parser error: golden v0 was read once, so a person checks the page before counting it.
