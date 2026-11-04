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


class DocumentDetail(DocumentSummary):
    sha256: str
    pages: list[PageInfo]
    sections: list[Section]
    run: Run
