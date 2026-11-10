# CHECKS: review figures

The figures that feed a KPI or a Sharia screen, for a person to accept or correct before they count (#23). Only consolidated figures of the inputs in `backend/src/bloomberg_invest/config/kpis/` are listed.

## Sub-features

- Counts: `TO CHECK`, `NEEDS REVIEW` (rejected figures, which can only be corrected) and `DONE`.
- "Checks are recorded as <name>", from `REVIEWER` in `.env`. Without it a dashed notice says how to set it, and no buttons show.
- Filters: `ALL COMPANIES` or one company, and `OPEN` (default), `NEEDS REVIEW`, `DONE`, `ALL`, kept in the URL as `?company=<ISIN>&status=<id>`.
- One region per filing; a row per value the filing states, problems first: rejected figures, then values marked `≠ STATED DIFFERENTLY ELSEWHERE`, then by statement, line item and newest year. `n SOURCES AGREE` when several passages state it.
- Each row: company and period, line item, basis, the KPIs it feeds; the value as extracted; the source cropped from the page image with the cell or quote highlighted (it opens the source viewer); the parsed value; the status and its actions.
- `ACCEPT` (disabled on a rejected figure). `CORRECT` offers the numbers of the same table row or paragraph, and a field to type the right value in the figure's unit. A refused check shows why under the buttons.
- A checked row reads "Accepted by <name> on <date>" (or "Corrected") with `REOPEN`. A row checked on this visit stays in place until the filter changes.
- In the source viewer, a figure's highlight bar says "Checked by <name> on <date>", "Corrected to <value> by ...", or "Not checked yet".
- At 1024 the PARSED column is hidden; at 390 each row stacks.

## How to get to it (user POV)

Click CHECKS in the top navigation, or open http://localhost:8080/checks.

## Driving it with Playwright

The filing is `getByRole("region", { name: "Maroc Telecom · Annual financial report 2025" })`; rows are list items named `<line item>, FY<year>: <status>`, for example `Revenue, FY2025: To check`. Buttons by name: `ACCEPT`, `CORRECT`, `CANCEL`, `REOPEN`; the row's picks are `getByRole("group", { name: "Cells in the same row" })` (`"Numbers in the same paragraph"` for a quote). The crop is a link named `Open the cell on page N in the source viewer`.

Proof: the first row needs review and can't be accepted; revenue FY2025's crop renders with a mark; ACCEPT turns it into "Accepted by ..."; its source viewer bar says "Checked by"; REOPEN puts it back to "To check".

## Gotchas

- Checks are never deleted: every journey run adds a Review and a reopening per viewport to the graph. That leaves the figures as they were, unchecked.
- Set `REVIEWER` in `.env` and restart the api service, or the journey's check fails at "the reviewer is set".
