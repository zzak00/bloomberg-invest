"""Score extracted figures against the golden figures.

For each golden figure, on its cited page:

- correct: a verified figure has the same line item, fiscal year, basis scope and number;
- unverified: the only such figure failed the check against its source;
- wrong_label: a verified figure has the same number and year, but another line item or scope;
- missing: none of the above.

Extracted figures that match no golden figure are counted as "extra". Golden v0 does not list every
figure on a page, so an extra is not necessarily wrong.
"""

import csv
import json
from collections import Counter
from pathlib import Path

from bakeoff.score import EXCLUDED_PAGES, number

OUTCOMES = ["correct", "wrong_label", "unverified", "missing"]


def fiscal_year(period: str) -> int:
    """FY2025 and 2025-12-31 are both fiscal year 2025."""
    return int(period[2:]) if period.startswith("FY") else int(period[:4])


def load_golden(path: Path) -> list[dict]:
    with path.open(newline="") as handle:
        return [
            row | {"page": int(row["page"]), "year": fiscal_year(row["period"])}
            for row in csv.DictReader(handle)
            if row["page"].isdigit() and int(row["page"]) not in EXCLUDED_PAGES and row["period"]
        ]


def outcome(golden: dict, figures: list[dict]) -> tuple[str, dict | None]:
    same_value = [
        f
        for f in figures
        if f["page"] == golden["page"]
        and f["fiscal_year"] == golden["year"]
        and number(f["value_as_written"]) == number(golden["value_as_written"])
    ]
    labelled = [
        f
        for f in same_value
        if f["line_item"] == golden["line_item"] and f["basis_scope"] == golden["basis_scope"]
    ]
    if any(f["verified"] for f in labelled):
        return "correct", next(f for f in labelled if f["verified"])
    if labelled:
        return "unverified", labelled[0]
    if any(f["verified"] for f in same_value):
        return "wrong_label", next(f for f in same_value if f["verified"])
    return "missing", None


def report(runs: list[dict], golden: list[dict]) -> str:
    lines = [
        "# Extractor bake-off against golden v0",
        "",
        f"{len(golden)} golden figures with a fiscal year (pages {sorted(EXCLUDED_PAGES)} excluded).",
        "",
        "| Deployment | Parser | Seconds | Input tokens | Output tokens | Extracted | Rejected by check | "
        + " | ".join(OUTCOMES)
        + " | Correct % | Extra |",
        "| --- | --- | --- | --- | --- | --- | --- | " + " | ".join("---" for _ in OUTCOMES) + " | --- | --- |",
    ]
    misses = []
    for run in runs:
        figures = run["figures"]
        results = [(g, *outcome(g, figures)) for g in golden]
        counts = Counter(o for _, o, _ in results)
        matched = {id(f) for _, _, f in results if f is not None}
        extra = sum(1 for f in figures if f["verified"] and id(f) not in matched)
        rejected = sum(1 for f in figures if not f["verified"])
        lines.append(
            f"| {run['deployment']} | {run['parser']} | {run['seconds']} | {run['usage']['input_tokens']} "
            f"| {run['usage']['output_tokens']} | {len(figures)} | {rejected} | "
            + " | ".join(str(counts[o]) for o in OUTCOMES)
            + f" | {100 * counts['correct'] / len(golden):.0f} % | {extra} |"
        )
        misses += [
            f"| {run['deployment']} | {o} | {g['page']} | {g['line_item']} | {g['basis_scope']} | {g['year']} "
            f"| {g['value_as_written']} | {g['raw_label']} | "
            + (f"{f['line_item']} / {f['basis_scope']} from {f['source_id']}" if f else "")
            + " |"
            for g, o, f in results
            if o != "correct"
        ]
    lines += [
        "",
        "## Not correct",
        "",
        "| Deployment | Outcome | Page | Line item | Scope | Year | Value | Label in report | Extractor said |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        *misses,
    ]
    return "\n".join(lines) + "\n"


def score(extracted_dir: Path, golden_path: Path) -> str:
    runs = [json.loads(path.read_text()) for path in sorted(extracted_dir.glob("*.json"))]
    return report(runs, load_golden(golden_path))
