# KPIs: the scorecard and the KPIs page

The quality KPIs, EBITDA margin and the Piotroski F-score (#27), computed in Python from a company's checked consolidated IFRS figures and declared dividends under `backend/src/bloomberg_invest/config/kpis/`. The KPIs page is generated from the same rules.

## Sub-features

- The dossier's `SCORECARD` tab: "CONSOLIDATED · IFRS · FY2025 · KPI V1" with one `FY<year>` button per fiscal year with values (the last computed by default, kept in the URL as `?tab=scorecard&year=2024`), the gate note, for a bank or insurer which KPIs apply, and with no Listing "Sector unknown …".
- QUALITY · 17: one row per KPI. A value in French format ("50,4 %", "1,0x", "9 095 MAD m") with a FY-2 to FY sparkline ("FY<year> only" with one point, naming its year), the sector median with its peer count or "sector: too few peers (n)" below 3, and the usual band with ▲, ▼ or ●. Without a value, "–" and why, naming each input and year: "Waiting for check: …" (pink), "Two values for: …", "Missing: …", "Not meaningful …". Gross margin reads "Not meaningful: the income statement is by nature: no gross profit".
- Hover or focus a KPI's name: its formula, each input with its value, page (a link to the source viewer) and "checked by <name> ✓" or "waiting for check", and the rule version. Escape closes it.
- PIOTROSKI F-SCORE: nine cells (passed filled, failed outlined, waiting dashed, not applicable faint with "–"), the legend, "n / 8" once the eight tests that apply have checked inputs, with "Score n of 8: gross margin up is not meaningful.", else "n passed · m waiting", and each test with its state and what it waits for.
- The payout ratio reads the dividend declared for the fiscal year, a dividend Fact: its input in the hover opens the fact inspector, which says "Feeds the payout ratio" with `ACCEPT · 4,00 dirhams`, then "Checked by <name> on <date>" with `UNDO`.
- A check or a reopening in CHECKS recomputes the KPIs reading the figure, written with the check in one transaction: only those values are superseded (the graph keeps the old ones). CHECKS lists the declared dividend under `DECLARED DIVIDENDS` ([checks.md](checks.md)).
- `KPIS` in the top navigation: the locked note, `VERSION HISTORY`, a search over names, formulas and inputs, theme filters with counts, and one row per KPI: KPI, theme, what it means, formula, inputs, how to read it (with its usual band), applies to, rule version. At 390 each KPI is a card of labelled fields.

## How to get to it (user POV)

On a company's dossier, click `SCORECARD`, or open http://localhost:8080/companies/MA0000011488?tab=scorecard. Click KPIS in the top navigation, or open http://localhost:8080/kpis.

## Driving it with Playwright

Quality rows are list items of `getByRole("list", { name: "Quality KPIs" })`; a KPI's name is a button named by its title (`EBITDA margin`), and its inputs are `.kpi-row:focus-within .kpi-tip` once that button has focus. The F-score is `getByRole("list", { name: /^Piotroski F-score: \d of 8 tests passed/ })`. Years are buttons of `getByRole("group", { name: "Fiscal year" })`. On the KPIs page, rows are `.kpis-table tbody tr` (at 390 the table is restyled as cards, which drops its table role), the search is `getByRole("searchbox", { name: "Search KPIs" })`, themes are buttons of `getByRole("group", { name: "Themes" })`.

Proof: 17 quality rows, each a value or "–" with a reason; focusing EBITDA margin lists EBITDA and revenue with their pages; nine F-score tests, gross margin up not applicable; `FY2024` shows FY2024's values and keeps the year in the URL; the payout ratio's declared dividend opens the inspector, ACCEPT reads "Checked by …" and UNDO puts it back; accepting revenue FY2025 in CHECKS drops it from EBITDA margin's reason and reopening puts it back; the KPIs page has 18 rows, LEVERAGE shows 3, searching "EBITDA" finds 2.

## Getting KPI values

Values are computed with each check, and at the end of the CLI's `ingest`, `extract` and `facts`. On a stack whose filing was ingested before #27, or after a new rule version, compute them once:

```bash
docker compose exec api bloomberg kpis
```

## Gotchas

- With nothing checked every KPI reads "–": the journey proves the computation through the reasons. To see values, check the inputs in CHECKS (the golden test checks every FY2025 input against `figures.csv`).
- Interest coverage, payout and the F-score's "no new shares" read "Missing" on the golden report: its extraction writes the interest expense and number of shares totals with a breakdown ("gross cost of debt", "at 31 December"), and a KPI reads the line item itself. So the F-score shows no score even with every other input checked.
- Revenue FY2024 reads "Two values" when both 36 699 (p. 4) and 36 704 (p. 9, adjusted) are checked: reopen one.
