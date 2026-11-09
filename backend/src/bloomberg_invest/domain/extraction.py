"""Extracting figures from one page (#19 R5, R6; the #10 design). Pure: the LLM call is elsewhere.

The LLM sees one page at a time: its paragraphs with ids, and its tables as HTML whose cells
carry ids. It returns figures that name a source id and copy the value as written; it never
returns coordinates and never computes. Python then turns each into a `FigureDraft`, checked
against its source: a figure whose value does not match is kept, rejected, with the reason.
"""

import html
import re
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from bloomberg_invest.domain.chunking import Box
from bloomberg_invest.domain.figures import (
    STANDARD,
    Period,
    Scope,
    matches_cell,
    matches_span,
    parse_unit,
    parse_value,
    period,
    scaled,
)
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.model import Bbox

DIGIT = re.compile(r"\d")
SENTENCE_END = re.compile(r"(?<=[.;!?])\s+")


@dataclass(frozen=True)
class SourceCell:
    """A stored table Cell, as extraction reads it."""

    id: str
    table: int  # the table's position in the document
    page: int
    row: int
    col: int
    col_span: int
    text: str
    bbox: Bbox


@dataclass(frozen=True)
class SourceParagraph:
    page: int
    text: str
    boxes: tuple[Box, ...]


@dataclass(frozen=True)
class PageSources:
    """One page as the LLM reads it, and what each id it may cite stands for."""

    page: int
    prompt: str
    cells: dict[str, SourceCell]
    paragraphs: dict[str, SourceParagraph]


class Rejection(StrEnum):
    """Why a proposed figure is not a Fact (#19 R6)."""

    unknown_source = "its source id is not on the page"
    value_differs = "its value differs from its cell"
    not_in_paragraph = "its value is not in its paragraph"
    unreadable_value = "its value is not one number"
    unknown_unit = "its unit names no currency, percentage or share count"
    unknown_line_item = "its line item is not in the label map"
    unknown_scope = "its scope is neither consolidated nor company-only"


@dataclass(frozen=True)
class CellPassage:
    cell_id: str


@dataclass(frozen=True)
class SpanPassage:
    """A range of a paragraph: the quoted value, in the paragraph's text and boxes."""

    page: int
    quote: str
    text: str
    boxes: tuple[Box, ...]


@dataclass(frozen=True)
class FigureDraft:
    """A figure the LLM proposed, parsed and checked; `rejected` says why it is not a Fact."""

    page: int
    line_item: str
    fiscal_year: int
    basis_scope: str
    breakdown: str
    source_id: str  # the id the LLM cited on the page
    value_as_written: str
    unit_scale: str  # the unit as the LLM named it
    label: str  # the filing's own wording: the row's label, or the sentence holding the value
    passage: CellPassage | SpanPassage | None
    basis_standard: str | None = None
    value: str | None = None  # exact decimal string in the base unit
    unit: str | None = None
    scale: int | None = None
    currency: str | None = None
    period: Period | None = None
    rejected: Rejection | None = None


def pages_to_extract(
    paragraphs: Sequence[SourceParagraph], cells: Sequence[SourceCell]
) -> list[int]:
    """Pages holding a table or a digit in their text: no other page can hold a figure."""
    pages = {c.page for c in cells}
    pages |= {p.page for p in paragraphs if DIGIT.search(p.text)}
    return sorted(pages)


def page_sources(
    page: int, paragraphs: Sequence[SourceParagraph], cells: Sequence[SourceCell]
) -> PageSources:
    """The page as the LLM sees it, with ids that are stable for the same parse."""
    by_id: dict[str, SourceParagraph] = {}
    parts = [f"Page {page}", "", "Paragraphs:"]
    for i, paragraph in enumerate(p for p in paragraphs if p.page == page):
        paragraph_id = f"p{page}.{i}"
        by_id[paragraph_id] = paragraph
        parts.append(f"[{paragraph_id}] {paragraph.text}")
    parts += ["", "Tables:"]
    tables: dict[int, list[SourceCell]] = defaultdict(list)
    for cell in cells:
        if cell.page == page:
            tables[cell.table].append(cell)
    by_cell: dict[str, SourceCell] = {}
    for i, table in enumerate(sorted(tables)):
        table_id = f"t{page}.{i}"
        by_cell |= {f"{table_id}.r{c.row}.c{c.col}": c for c in tables[table]}
        parts.append(_table_html(tables[table], table_id))
    return PageSources(page, "\n".join(parts), by_cell, by_id)


def _table_html(cells: list[SourceCell], table_id: str) -> str:
    rows: dict[int, list[SourceCell]] = defaultdict(list)
    for cell in cells:
        rows[cell.row].append(cell)
    lines = [f'<table id="{table_id}">']
    for row in sorted(rows):
        tds = "".join(
            f'<td id="{table_id}.r{c.row}.c{c.col}"'
            + (f' colspan="{c.col_span}"' if c.col_span > 1 else "")
            + f">{html.escape(c.text)}</td>"
            for c in sorted(rows[row], key=lambda c: c.col)
        )
        lines.append(f"<tr>{tds}</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def instructions(prompt: str, label_map: LabelMap) -> str:
    """The prompt followed by every line item with its definition."""
    return prompt + "\n".join(f"- {i.name}: {i.definition}" for i in label_map.items.values())


def schema(label_map: LabelMap) -> dict[str, Any]:
    """The JSON the LLM must return: strict, so every field is present and typed."""
    fields = {
        "line_item": {"type": "string", "enum": list(label_map.items)},
        "fiscal_year": {"type": "integer"},
        "basis_scope": {"type": "string", "enum": [s.value for s in Scope]},
        "breakdown": {"type": "string"},
        "source_id": {"type": "string"},
        "value_as_written": {"type": "string"},
        "unit_scale": {"type": "string"},
    }
    return {
        "type": "object",
        "properties": {
            "figures": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": fields,
                    "required": list(fields),
                    "additionalProperties": False,
                },
            }
        },
        "required": ["figures"],
        "additionalProperties": False,
    }


def drafts(
    response: dict[str, Any], sources: PageSources, label_map: LabelMap
) -> list[FigureDraft]:
    """Each figure the LLM returned for the page, parsed and checked against its source."""
    return [_draft(item, sources, label_map) for item in response["figures"]]


def _draft(item: dict[str, Any], sources: PageSources, label_map: LabelMap) -> FigureDraft:
    written, source_id = item["value_as_written"], item["source_id"]
    cell = sources.cells.get(source_id)
    paragraph = sources.paragraphs.get(source_id)
    passage: CellPassage | SpanPassage | None = None
    label = ""
    if cell is not None:
        passage, label = CellPassage(cell.id), _row_label(cell, sources.cells.values())
    elif paragraph is not None:
        label = _sentence(written, paragraph.text)
        passage = SpanPassage(paragraph.page, written, paragraph.text, paragraph.boxes)
    draft = FigureDraft(
        page=sources.page,
        line_item=item["line_item"],
        fiscal_year=item["fiscal_year"],
        basis_scope=item["basis_scope"],
        breakdown=item["breakdown"],
        source_id=source_id,
        value_as_written=written,
        unit_scale=item["unit_scale"],
        label=label,
        passage=passage,
    )
    value, unit = parse_value(written), parse_unit(item["unit_scale"])
    line_item = label_map.items.get(item["line_item"])
    if cell is None and paragraph is None:
        reason = Rejection.unknown_source
    elif cell is not None and not matches_cell(written, cell.text):
        reason = Rejection.value_differs
    elif paragraph is not None and not matches_span(written, paragraph.text):
        reason = Rejection.not_in_paragraph
    elif value is None:
        reason = Rejection.unreadable_value
    elif unit is None:
        reason = Rejection.unknown_unit
    elif line_item is None:
        reason = Rejection.unknown_line_item
    elif item["basis_scope"] not in {s.value for s in Scope}:
        reason = Rejection.unknown_scope
    else:
        return replace(
            draft,
            basis_standard=STANDARD[Scope(item["basis_scope"])],
            value=scaled(value, unit),
            unit=unit.unit,
            scale=unit.scale,
            currency=unit.currency,
            period=period(item["fiscal_year"], line_item.kind),
        )
    return replace(draft, rejected=reason)


def _row_label(cell: SourceCell, cells: Iterable[SourceCell]) -> str:
    """The text cells left of the figure in its row: the line as the filing names it."""
    left = sorted(
        (
            c
            for c in cells
            if c.table == cell.table
            and c.row == cell.row
            and c.col < cell.col
            and c.text.strip()
            and parse_value(c.text) is None
        ),
        key=lambda c: c.col,
    )
    return " ".join(" ".join(c.text.split()) for c in left)


def _sentence(value: str, paragraph: str) -> str:
    """The sentence of the paragraph holding the value, or the paragraph if none does."""
    for sentence in SENTENCE_END.split(" ".join(paragraph.split())):
        if matches_span(value, sentence):
            return sentence
    return " ".join(paragraph.split())
