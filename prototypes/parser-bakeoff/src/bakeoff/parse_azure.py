"""Parse a PDF with Azure Document Intelligence (prebuilt-layout) into the parser-neutral format.

Needs AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY in the environment.

The free F0 tier takes files up to 4 MB and reads only their first 2 pages, so on F0 the PDF is
sent in slices of `pages_per_request` pages. A table that crosses a slice boundary is then cut in
two, so multi-page table results are only meaningful when the whole PDF goes in one request.
"""

import io
import json
import os
import time
from importlib.metadata import version
from pathlib import Path

import pypdfium2
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentContentFormat
from azure.core.credentials import AzureKeyCredential

from bakeoff.tables import Cell, Paragraph, ParseResult, Table

KINDS = {"columnHeader": "column_header", "rowHeader": "row_header"}


def slices(pdf: Path, pages_per_request: int | None) -> list[tuple[int, bytes]]:
    """(page offset, PDF bytes) for each request; the whole file when no slice size is given."""
    if not pages_per_request:
        return [(0, pdf.read_bytes())]
    source = pypdfium2.PdfDocument(pdf)
    parts = []
    for start in range(0, len(source), pages_per_request):
        part = pypdfium2.PdfDocument.new()
        part.import_pages(source, list(range(start, min(start + pages_per_request, len(source)))))
        buffer = io.BytesIO()
        part.save(buffer)
        parts.append((start, buffer.getvalue()))
    return parts


def page_markdown(result, offset: int) -> str:
    """Azure's own Markdown for each page of one request, each page headed by its number."""
    return "".join(
        f"<!-- page {offset + page.page_number} -->\n"
        + "".join(result.content[s.offset : s.offset + s.length] for s in page.spans or [])
        + "\n\n"
        for page in result.pages or []
    )


def parse(pdf: Path, raw_out: Path, pages_per_request: int | None = None) -> ParseResult:
    """Also writes Azure's Markdown next to the raw output, as raw_out with a .md suffix."""
    client = DocumentIntelligenceClient(
        os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"],
        AzureKeyCredential(os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]),
    )
    tables, paragraphs, raw, markdown, page_count = [], [], [], "", 0
    started = time.monotonic()
    for offset, body in slices(pdf, pages_per_request):
        result = client.begin_analyze_document(
            "prebuilt-layout",
            body=body,
            content_type="application/octet-stream",
            output_content_format=DocumentContentFormat.MARKDOWN,
        ).result()
        markdown += page_markdown(result, offset)
        raw.append({"page_offset": offset, "result": result.as_dict()})
        page_count += len(result.pages or [])

        for table in result.tables or []:
            cells = [
                Cell(
                    row=cell.row_index,
                    col=cell.column_index,
                    text=cell.content,
                    kind=KINDS.get(cell.kind or "", "content"),
                    col_span=cell.column_span or 1,
                )
                for cell in table.cells
            ]
            pages = sorted({offset + region.page_number for region in table.bounding_regions or []})
            caption = table.caption.content if table.caption else ""
            tables.append(Table(pages, caption, cells))

        paragraphs += [
            Paragraph(offset + paragraph.bounding_regions[0].page_number, paragraph.content)
            for paragraph in result.paragraphs or []
            if paragraph.bounding_regions
        ]
    seconds = time.monotonic() - started
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw_out.write_text(json.dumps(raw, ensure_ascii=False))
    raw_out.with_suffix(".md").write_text(markdown)

    sliced = f" in {pages_per_request}-page slices" if pages_per_request else ""
    return ParseResult(
        parser="azure-layout",
        version=f"{result.model_id} {result.api_version} sdk {version('azure-ai-documentintelligence')}{sliced}",
        seconds=round(seconds, 1),
        page_count=page_count,
        tables=tables,
        paragraphs=paragraphs,
    )
