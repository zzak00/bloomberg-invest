"""Parse a PDF with Azure Document Intelligence (prebuilt-layout) into the parser-neutral format.

Needs AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT and AZURE_DOCUMENT_INTELLIGENCE_KEY in the environment.
"""

import json
import os
import time
from importlib.metadata import version
from pathlib import Path

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.core.credentials import AzureKeyCredential

from bakeoff.tables import Cell, Paragraph, ParseResult, Table

KINDS = {"columnHeader": "column_header", "rowHeader": "row_header"}


def parse(pdf: Path, raw_out: Path) -> ParseResult:
    client = DocumentIntelligenceClient(
        os.environ["AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT"],
        AzureKeyCredential(os.environ["AZURE_DOCUMENT_INTELLIGENCE_KEY"]),
    )
    started = time.monotonic()
    with pdf.open("rb") as body:
        poller = client.begin_analyze_document(
            "prebuilt-layout", body=body, content_type="application/octet-stream"
        )
        result = poller.result()
    seconds = time.monotonic() - started
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    raw_out.write_text(json.dumps(result.as_dict(), ensure_ascii=False))

    tables = []
    for table in result.tables or []:
        cells = [
            Cell(
                row=cell.row_index,
                col=cell.column_index,
                text=cell.content,
                kind=KINDS.get(cell.kind or "", "content"),
            )
            for cell in table.cells
        ]
        pages = sorted({region.page_number for region in table.bounding_regions or []})
        caption = table.caption.content if table.caption else ""
        tables.append(Table(pages, caption, cells))

    paragraphs = [
        Paragraph(paragraph.bounding_regions[0].page_number, paragraph.content)
        for paragraph in result.paragraphs or []
        if paragraph.bounding_regions
    ]
    return ParseResult(
        parser="azure-layout",
        version=f"{result.model_id} {result.api_version} sdk {version('azure-ai-documentintelligence')}",
        seconds=round(seconds, 1),
        page_count=len(result.pages or []),
        tables=tables,
        paragraphs=paragraphs,
    )
