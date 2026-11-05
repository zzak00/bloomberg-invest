"""Write models and the rules they enforce: what a parse produces and what ingest records.

Terms follow AGENTS.md. Boxes are in PDF points with a top-left origin: (left, top, right, bottom).
"""

from datetime import datetime
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

Bbox = tuple[float, float, float, float]
Isin = Annotated[str, Field(pattern=r"^[A-Z]{2}[A-Z0-9]{9}[0-9]$")]


class DocType(StrEnum):
    annual_report = "annual_report"
    half_year_report = "half_year_report"
    issuer_page = "issuer_page"


class Organisation(BaseModel):
    """The Organisation a filing comes from. Keyed by the ISIN the operator gives until
    Listings (which own the ISIN in AGENTS.md) arrive in #24."""

    isin: Isin
    name: str = Field(min_length=1)


class DocumentMeta(BaseModel):
    """What the operator states about a filing when ingesting it."""

    issuer: Organisation
    doc_type: DocType
    fiscal_year: int = Field(ge=1990, le=2100)
    regulator: str = "AMMC"
    source_url: str | None = None


class PageInfo(BaseModel):
    number: int = Field(ge=1)
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class SectionNode(BaseModel):
    title: str = Field(min_length=1)
    level: int = Field(ge=1)
    page: int = Field(ge=1)
    bbox: Bbox | None = None
    children: list["SectionNode"] = []


class ParsedDocument(BaseModel):
    pages: list[PageInfo] = Field(min_length=1)
    sections: list[SectionNode]

    @model_validator(mode="after")
    def _sections_sit_on_parsed_pages(self) -> "ParsedDocument":
        numbers = {p.number for p in self.pages}
        stack = list(self.sections)
        while stack:
            section = stack.pop()
            if section.page not in numbers:
                raise ValueError(section_not_on_parsed_page(section.title, section.page))
            stack.extend(section.children)
        return self


def section_not_on_parsed_page(title: str, page: int) -> str:
    """The error for a section whose page was not parsed."""
    return f"section {title!r} is on page {page}, not parsed"


class RunStep(StrEnum):
    """The processing steps a Run records (AGENTS.md); later steps add theirs."""

    parse = "parse"
    chunk = "chunk"


class RunStatus(StrEnum):
    succeeded = "succeeded"
    failed = "failed"


class RunInfo(BaseModel):
    """One execution of a processing step (ADR 0002)."""

    step: RunStep
    tool: str
    tool_version: str
    config: dict[str, str]
    started_at: datetime
    finished_at: datetime
    status: RunStatus = RunStatus.succeeded
    error: str | None = None
    # The tool's own full output, relative to the data directory, for later steps to reuse.
    output: str | None = None
