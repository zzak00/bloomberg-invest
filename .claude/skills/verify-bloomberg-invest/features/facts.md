# Facts: dossier sections, inspector, CHECKS Names

The eight other kinds of fact (#24): shareholdings, board seats, audit mandates, listings, consolidation, dividends, auditor opinions and related-party agreements. Each is read by `bloomberg facts`, checked against the passage it quotes (D2), and names Organisations or Persons through Aliases (D3).

## Sub-features

- The dossier's `FACTS · n` tab: one section per kind (Ownership, Holdings, Subsidiaries, Board, Auditors, Dividends, Listings, Related-party agreements), only those with rows. A row is one value shown: who it is about, the value, its as-of date or fiscal year, and its review mark (`≠ · 2 VALUES` for a Conflict, `KEPT`, `NAME TO CHECK`). "n facts wait for a name to be checked · CHECKS →" counts the facts that can't show yet because a company they name isn't linked, and links to CHECKS Names.
- A value opens the fact inspector, kept in the URL as `?tab=facts&fact=<id>`: a side panel at 1440 and 1024, a full-width sheet at 390. It shows the fact in one sentence with its value marked, AS OF or PERIOD, BASIS where the kind has one, RECORDED and REVIEW, each name as written and what it links to (or "not linked yet · CHECKS"), the evidence status line, the quote on paper, and `OPEN SOURCE →` to the source viewer on the highlighted passage. Escape or `ESC` closes it.
- A Conflict (S3b): `TWO FILINGS DISAGREE` (or `TWO PASSAGES OF ONE FILING DISAGREE`), the sentence with both values, a card per value with its filing, page, date, recorded date and quote, and which one the dossier shows and why. `KEEP A` / `KEEP B` record a Review on that fact (D5); "Kept B · … by <name> on <date>" then has `UNDO`.
- CHECKS has three tabs: `FIGURES · n` (#23), `NAMES · n` and `REJECTED FACTS · n`, kept in the URL as `?tab=names` or `?tab=facts`.
- NAMES (S7b): each name no rule linked to exactly one Organisation or Person, to check first. The name as written, what the extractor read it as, the filing and page (a link to the source viewer), and the quote. `SAME AS` on a candidate or on any known one from the list, `NEW ORGANISATION OR PERSON` (name and kind), or `NEITHER`. A decision holds for every filing writing the name and reads "Same as …", "New: …" or "Neither an Organisation nor a Person", with who and when and `UNDO`.
- REJECTED FACTS: each fact the check refused, with its reason ("Rejected: its year is not on its page"), the quote, and a link to its page.

## How to get to it (user POV)

On a company's dossier, click `FACTS`. Or open http://localhost:8080/companies/MA0000011488?tab=facts, and http://localhost:8080/checks?tab=names.

## Driving it with Playwright

Sections are regions named `OWNERSHIP · n`; a value is a button named by its sentence, for example `Etisalat holds 53 % of Maroc Telecom, 31/12/2025` (`…, 2 values disagree` for a Conflict). The inspector is `getByRole("dialog", { name: "Fact inspector" })`; a Conflict's cards are `getByRole("list", { name: "Values at this date" })`. Names rows are list items of `getByRole("list", { name: "Names" })`, named `<written names>: to check`.

Proof: the inspector's sentence reads "… holds … of …" with AS OF, RECORDED and REVIEW (PERIOD and BASIS for an audit mandate); `OPEN SOURCE →` highlights the passage; a Conflict says which value is shown and why, and Keep then Undo puts it back; `NEITHER` and `SAME AS`, each undone, put a name back to check. `NEW ORGANISATION OR PERSON` is not driven: an Organisation, once created, stays in the graph after the Undo.

## Getting facts without a live model

Run the facts pass from the recorded answers (the recording the golden harness made), from the repository root:

```bash
docker compose run --rm -e LLM_REPLAY=/data/recordings/<sha256 prefix>-extract-facts-v1.jsonl \
  facts <document id>
```

## Gotchas

- The journey's Conflict step needs a row with two values at one date, which a single filing rarely has: the journey seeds one, a copy of a Maroc Telecom shareholding with another percentage marked `seeded: 'verify-journey'`, and deletes it and its Reviews at the end (and at the start, after a run that stopped).
- Keep, Undo and the Names decisions add Reviews to the graph each run; the journey undoes each, so the data reads as before.
- Set `REVIEWER` in `.env`, or no Keep or Names buttons show.
