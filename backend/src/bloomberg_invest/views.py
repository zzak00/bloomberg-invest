"""Read models: the shapes the store returns and the API serves."""

from datetime import datetime

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


class SearchHit(BaseModel):
    """A Chunk search returned, with where to find it."""

    chunk_id: str
    text: str
    pages: list[int]
    # (page, left, top, right, bottom) in PDF points, top-left origin: the source viewer draws them.
    boxes: list[tuple[int, float, float, float, float]]
    section_path: list[str]
    document: DocumentRef


class DocumentDetail(DocumentSummary):
    sha256: str
    pages: list[PageInfo]
    sections: list[Section]
    run: Run
