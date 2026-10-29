"""Parse a PDF with Docling, locally, into the parser-neutral format."""

import time
from importlib.metadata import version
from pathlib import Path

from docling.document_converter import DocumentConverter

from bakeoff.tables import Cell, Paragraph, ParseResult, Table


def parse(pdf: Path, raw_out: Path) -> ParseResult:
    started = time.monotonic()
    document = DocumentConverter().convert(pdf).document
    seconds = time.monotonic() - started
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    document.save_as_json(raw_out)

    tables = []
    for table in document.tables:
        cells = [
            Cell(
                row=cell.start_row_offset_idx,
                col=cell.start_col_offset_idx,
                text=cell.text,
                kind=(
                    "column_header"
                    if cell.column_header
                    else "row_header"
                    if cell.row_header
                    else "content"
                ),
            )
            for cell in table.data.table_cells
        ]
        pages = sorted({prov.page_no for prov in table.prov})
        tables.append(Table(pages, table.caption_text(document), cells))

    paragraphs = [
        Paragraph(item.prov[0].page_no, item.text)
        for item in document.texts
        if item.prov and item.text
    ]
    return ParseResult(
        parser="docling",
        version=version("docling"),
        seconds=round(seconds, 1),
        page_count=document.num_pages(),
        tables=tables,
        paragraphs=paragraphs,
    )
