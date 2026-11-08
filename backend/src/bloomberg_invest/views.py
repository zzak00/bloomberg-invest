"""Read models: the shapes the store returns and the API serves."""

from datetime import datetime
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


class Chunk(BaseModel):
    """A Chunk with where to find it: what search returns and the source viewer highlights."""

    id: str
    kind: Literal["text", "table"]
    text: str
    pages: list[int]
    boxes: list[Box]  # the regions of its blocks, which the source viewer highlights
    section_path: list[str]
    document: DocumentRef


class DocumentDetail(DocumentSummary):
    sha256: str
    pages: list[PageInfo]
    sections: list[Section]
    run: Run
