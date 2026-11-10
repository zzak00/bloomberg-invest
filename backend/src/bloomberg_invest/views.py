"""Read models: the shapes the store returns and the API serves."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.domain.model import Bbox, DocType, Organisation, PageInfo, RunInfo


class Section(BaseModel):
    id: str
    title: str
    level: int
    page: int
    bbox: Bbox | None
    children: list["Section"] = []


class Run(RunInfo):
    id: str


class DocumentSummary(BaseModel):
    id: str
    issuer: Organisation
    doc_type: DocType
    fiscal_year: int
    regulator: str
    source_url: str | None
    page_count: int
    ingested_at: datetime


class DocumentRef(BaseModel):
    id: str
    issuer: Organisation
    doc_type: DocType
    fiscal_year: int


class Box(BaseModel):
    """A region of a page in PDF points, top-left origin."""

    page: int
    left: float
    top: float
    right: float
    bottom: float


class TablePart(BaseModel):
    """Which part of a split table a Chunk is: parts of one table share `table_id`."""

    table_id: str
    part: int
    parts: int


class Chunk(BaseModel):
    """A Chunk with where to find it: what search returns and the source viewer highlights."""

    id: str
    kind: Literal["text", "table"]
    text: str
    pages: list[int]
    boxes: list[Box]  # the regions of its blocks, which the source viewer highlights
    section_path: list[str]
    table: TablePart | None = None  # tables only
    document: DocumentRef


class DocumentDetail(DocumentSummary):
    sha256: str
    pages: list[PageInfo]
    sections: list[Section]
    run: Run


class Passage(BaseModel):
    """The exact span a Fact cites: a table cell, or a quoted range of a paragraph."""

    kind: Literal["cell", "span"]
    page: int
    boxes: list[Box]  # what the source viewer highlights: the cell, or the quote
    text: str  # the cell's text, or the paragraph's
    quote: str | None = None  # spans: the value as quoted


class Review(BaseModel):
    """The check in force on a figure (#19 R9): a person accepted it or gave the right value."""

    id: str
    verdict: Literal["accepted", "corrected"]
    reviewer: str
    reviewed_at: datetime
    value_as_written: str | None = None  # corrected: the right value, as the person gave it
    value: str | None = None  # corrected: the right value in the base unit


class RecordedReview(BaseModel):
    """A check as recorded: accepted, corrected, or reopened to undo the one before."""

    id: str
    verdict: Literal["accepted", "corrected", "reopened"]
    reviewer: str
    reviewed_at: datetime
    value_as_written: str | None = None
    value: str | None = None


class Figure(BaseModel):
    """A financial figure Fact (#19 R5, R6): checked against its Passage before it was stored."""

    id: str
    line_item: str  # a line item of the label map
    label: str  # the filing's own wording
    value: str  # exact decimal in the base unit: "36681000000"
    value_as_written: str  # "36 681"
    unit_as_written: str  # as the LLM read it: "MAD millions"
    unit: str  # "MAD", "%", "shares", "MAD/share"
    scale: int  # what the written value is multiplied by: 1, 1 000, 1 000 000...
    currency: str | None
    fiscal_year: int
    period_start: date | None  # flows
    period_end: date | None
    as_of: date | None  # stocks
    basis_scope: Scope
    basis_standard: str
    breakdown: str  # empty for the line item itself, else which part of it
    recorded_at: datetime
    document: DocumentRef
    passage: Passage
    review: Review | None  # the check in force; None when nobody checked it (#23 AC4)
    # It feeds a KPI or screen and nobody checked it yet (#19 R10). Set by the service layer,
    # which knows the KPI rules; the store leaves it False.
    needs_review: bool = False


class FigureDetail(Figure):
    """A figure with its line item's title in the current label map, as the viewer names it."""

    line_item_title: str


class Company(BaseModel):
    """An issuer's dossier: its filings."""

    issuer: Organisation
    documents: list[DocumentSummary]


class FigureValue(BaseModel):
    """One value a line item takes in a year, and every figure stating it, rounded or not."""

    shown: Figure  # the one a click opens: in the row's unit, from the earliest page
    sources: list[Figure]


class FigureYear(BaseModel):
    fiscal_year: int
    values: list[FigureValue]  # more than one: the filing disagrees with itself


class FigureRow(BaseModel):
    """A line item, or one breakdown of it, in one currency, by fiscal year."""

    line_item: str
    title: str  # the line item's title in the label map
    breakdown: str  # empty for the line item itself
    currency: str  # the currency, or the unit for a percentage or a share count
    unit: str  # the unit and scale most of its figures are written in
    scale: int
    years: list[FigureYear]  # newest first, only years with a value


class StatementFigures(BaseModel):
    key: str
    title: str
    rows: list[FigureRow]  # in the label map's order, the filing's main currency first


class ScopeFigures(BaseModel):
    scope: Scope
    years: list[int]  # every fiscal year with a figure on this basis, newest first
    statements: list[StatementFigures]  # in the label map's order, only those with rows


class FigureGrid(BaseModel):
    """An issuer's current figures as the dossier lists them, on each basis."""

    count: int  # every current figure, on both bases
    scopes: list[ScopeFigures]


class Proposed(BaseModel):
    """A RejectedFigure: what the LLM proposed, and why the check refused it (#19 R6). It has no
    parsed value; a person can only correct it."""

    id: str
    line_item: str
    label: str
    value_as_written: str
    unit_as_written: str
    fiscal_year: int
    basis_scope: Scope | None
    breakdown: str
    page: int  # the page the LLM read
    reason: str
    document: DocumentRef
    passage: Passage | None  # None when the id it cited is not on the page
    review: Review | None


class CheckRow(BaseModel):
    """One value to check: every figure of one filing stating it, or one rejected figure."""

    figure_ids: list[str]  # what a check of this row reviews; the one shown first
    document: DocumentRef
    line_item: str
    title: str  # the line item's title in the label map
    statement: str  # its statement's title
    breakdown: str
    fiscal_year: int
    basis_scope: Scope | None
    period_start: date | None
    period_end: date | None
    as_of: date | None
    label: str  # the filing's own wording
    value_as_written: str
    unit_as_written: str
    value: str | None  # parsed, in the base unit; None for a rejected figure
    unit: str | None
    scale: int | None
    currency: str | None
    passage: Passage | None  # the source shown: the earliest page's
    page: int  # the page it was read on: its passage's, or the page the LLM read
    sources: int  # how many passages of the filing state it
    conflict: bool  # the filing states another value for the same line item and year
    rejected: str | None  # why the check refused it, for a rejected figure
    feeds: list[str]  # the KPIs and screens it feeds
    review: Review | None
    status: Literal["to_check", "needs_review", "accepted", "corrected"]


class CheckCounts(BaseModel):
    to_check: int
    needs_review: int  # rejected figures: they can only be corrected
    done: int


class CheckGroup(BaseModel):
    document: DocumentRef
    rows: list[CheckRow]


class CheckQueue(BaseModel):
    """CHECKS (#19 R9): the figures that feed a KPI or screen, problems first."""

    reviewer: str | None  # who checks on this app; None until REVIEWER is set
    counts: CheckCounts  # for the company asked, whatever the status filter
    companies: list[Organisation]  # every company with something to check
    groups: list[CheckGroup]  # one per filing


class Candidate(BaseModel):
    """A value a correction can pick from the figure's own source: a cell of the same table row,
    or a number in the same paragraph."""

    kind: Literal["cell", "quote"]
    value_as_written: str
    cell_id: str | None = None  # cells
    context: str  # the column's header for a cell, the words around a quote
