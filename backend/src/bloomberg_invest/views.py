"""Read models: the shapes the store returns and the API serves."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

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
    boxes: list[Box]  # what the source viewer highlights: the cell, or the quote's paragraph
    text: str  # the cell's text, or the paragraph's
    quote: str | None = None  # spans: the value as quoted


class Figure(BaseModel):
    """A financial figure Fact (#19 R5, R6): checked against its Passage before it was stored."""

    id: str
    line_item: str
    line_item_title: str
    statement: str  # a key of `Company.statements`
    label: str  # the filing's own wording
    value: str  # exact decimal in the base unit: "36681000000"
    value_as_written: str  # "36 681"
    unit: str  # "MAD", "%", "shares", "MAD/share"
    scale: int  # what the written value is multiplied by: 1, 1 000, 1 000 000...
    currency: str | None
    fiscal_year: int
    period_start: date | None  # flows
    period_end: date | None
    as_of: date | None  # stocks
    basis_scope: Literal["consolidated", "company-only"]
    basis_standard: str
    breakdown: str  # empty for the line item itself, else which part of it
    recorded_at: datetime
    document: DocumentRef
    passage: Passage


class Statement(BaseModel):
    key: str
    title: str
    line_items: list[str]  # in the label map's order, which the dossier lists them in


class Company(BaseModel):
    """An issuer's dossier: its filings, and how its figures are grouped."""

    issuer: Organisation
    documents: list[DocumentSummary]
    statements: list[Statement]  # in the order the dossier lists them
