"""Score parser outputs against the golden figures.

For each golden figure, look in the parser's tables on the cited page for a cell holding the
same number, then check that the cell sits in the right row and column:

- exact: value, row label and column label all match;
- row_only: value and row label match, column label doesn't;
- value_only: the value is in a table on the page, but in the wrong row;
- merged_cell: the value is only inside a cell holding several numbers;
- in_text: the value is only in the page's paragraphs;
- missing: the value is nowhere on the page.

A golden figure that cites running text, not a table, counts as exact when it is found in the
page's paragraphs.

Pages excluded from golden v0 (no text layer or unreadable) are skipped.
"""

import csv
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from bakeoff.tables import Cell, ParseResult, Table

EXCLUDED_PAGES = {26, 58}
OUTCOMES = ["exact", "row_only", "value_only", "merged_cell", "in_text", "missing"]
NUMERIC = re.compile(r"[\s(\-−–]*\d[\d\s\u00a0\u202f.,]*%?[\s)]*")


@dataclass
class Golden:
    line_item: str
    period: str
    value: str
    page: int
    table_title: str
    row_label: str
    column_label: str


@dataclass
class Score:
    golden: Golden
    outcome: str


def load_golden(path: Path) -> list[Golden]:
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        Golden(
            line_item=row["line_item"],
            period=row["period"],
            value=row["value_as_written"],
            page=int(row["page"]),
            table_title=row["table_title"],
            row_label=row["row_label"],
            column_label=row["column_label"],
        )
        for row in rows
        if row["page"].isdigit() and int(row["page"]) not in EXCLUDED_PAGES
    ]


def number(text: str) -> str:
    """The digits, decimal comma and sign of a cell, ignoring spaces of every width."""
    text = text.strip()
    negative = text.startswith(("-", "−", "–")) or (
        text.startswith("(") and text.endswith(")")
    )
    digits = re.sub(r"[^\d,]", "", text)
    return ("-" if negative and digits else "") + digits


def is_number(text: str) -> bool:
    """True for a cell that is a single number, not a label with a footnote digit."""
    return bool(NUMERIC.fullmatch(text.strip()))


def label(text: str) -> str:
    """Lowercase, no accents, no footnote markers, single spaces."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"\(\d+\)|\*+|\(\w\)$", " ", text.lower())
    text = re.sub(r"[^a-z0-9%]+", " ", text)
    return " ".join(text.split())


def similar(wanted: str, found: str) -> bool:
    wanted, found = label(wanted), label(found)
    if not wanted or not found:
        return False
    return wanted in found or SequenceMatcher(None, wanted, found).ratio() >= 0.8


def row_matches(table: Table, cell: Cell, wanted: str) -> bool:
    last = wanted.split(">")[-1]
    return any(
        similar(last, other.text)
        for other in table.cells
        if other.row == cell.row and other.col < cell.col and not is_number(other.text)
    )


def column_matches(table: Table, cell: Cell, wanted: str) -> bool:
    parts = [part for part in wanted.split(">") if part.strip()]
    headers = [
        other.text
        for other in table.cells
        if other.col == cell.col
        and other.row < cell.row
        and other.kind != "content"
        or other.col == cell.col
        and other.row < cell.row
        and not is_number(other.text)
    ]
    return bool(parts) and all(
        any(similar(part, header) for header in headers) for part in parts
    )


def score_one(result: ParseResult, golden: Golden) -> str:
    wanted = number(golden.value)
    tables = [table for table in result.tables if golden.page in table.pages]
    hits = [
        (table, cell)
        for table in tables
        for cell in table.cells
        if number(cell.text) == wanted
    ]
    if hits:
        if any(
            row_matches(table, cell, golden.row_label)
            and column_matches(table, cell, golden.column_label)
            for table, cell in hits
        ):
            return "exact"
        if any(row_matches(table, cell, golden.row_label) for table, cell in hits):
            return "row_only"
        return "value_only"
    numbers_in_cells = (
        re.findall(
            r"-?\d{1,3}(?:[\s\u00a0\u202f]\d{3})+(?:,\d+)?|-?\d+(?:,\d+)?", cell.text
        )
        for table in tables
        for cell in table.cells
    )
    if any(
        len(found) > 1 and wanted in (number(n) for n in found)
        for found in numbers_in_cells
    ):
        return "merged_cell"
    page_text = " ".join(p.text for p in result.paragraphs if p.page == golden.page)
    if wanted and wanted in re.sub(r"[^\d,\-]", "", page_text.replace(" ", "")):
        return "exact" if not golden.table_title else "in_text"
    return "missing"


def score(result: ParseResult, golden: list[Golden]) -> list[Score]:
    return [Score(item, score_one(result, item)) for item in golden]


def report(results: list[ParseResult], golden: list[Golden]) -> str:
    lines = [
        "# Parser bake-off against golden v0",
        "",
        f"{len(golden)} golden figures (pages {sorted(EXCLUDED_PAGES)} excluded).",
        "",
        "| Parser | Version | Seconds | Pages | Tables | Multi-page tables | "
        + " | ".join(OUTCOMES)
        + " | Exact % |",
        "| --- | --- | --- | --- | --- | --- | "
        + " | ".join("---" for _ in OUTCOMES)
        + " | --- |",
    ]
    misses = []
    for result in results:
        scores = score(result, golden)
        counts = Counter(s.outcome for s in scores)
        multi = sum(1 for table in result.tables if len(table.pages) > 1)
        exact = 100 * counts["exact"] / len(scores) if scores else 0
        lines.append(
            f"| {result.parser} | {result.version} | {result.seconds} | {result.page_count} "
            f"| {len(result.tables)} | {multi} | "
            + " | ".join(str(counts[outcome]) for outcome in OUTCOMES)
            + f" | {exact:.0f} % |"
        )
        misses += [
            f"| {result.parser} | {s.outcome} | {s.golden.page} | {s.golden.line_item} "
            f"| {s.golden.period} | {s.golden.value} | {s.golden.row_label} | {s.golden.column_label} |"
            for s in scores
            if s.outcome != "exact"
        ]
    lines += [
        "",
        "## Not exact",
        "",
        "| Parser | Outcome | Page | Line item | Period | Value | Row | Column |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        *misses,
    ]
    return "\n".join(lines) + "\n"
