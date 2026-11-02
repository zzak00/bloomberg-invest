"""Parse a PDF with Docling, locally, into the parser-neutral format.

Variants differ only in the table structure model:
- docling: TableFormer v1, accurate mode (Docling's default);
- docling-nomatch: TableFormer v1 defining the cells itself, ignoring the PDF's text cells;
- docling-v2: TableFormerV2 (a preview model), matching its cells to the PDF's text cells;
- docling-v2-nomatch: TableFormerV2 defining the cells itself, ignoring the PDF's text cells, which
  can be merged across columns.
"""

import time
from importlib.metadata import version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableStructureOptions,
    TableStructureV2Options,
)
from docling.document_converter import DocumentConverter, PdfFormatOption

from bakeoff.tables import Cell, Paragraph, ParseResult, Table


VARIANTS = {
    "docling": TableStructureOptions(),
    "docling-nomatch": TableStructureOptions(do_cell_matching=False),
    "docling-v2": TableStructureV2Options(),
    "docling-v2-nomatch": TableStructureV2Options(do_cell_matching=False),
}


def page_markdown(document) -> str:
    """Docling's own Markdown for each page, each page headed by its number."""
    return "".join(
        f"<!-- page {page} -->\n{document.export_to_markdown(page_no=page)}\n\n"
        for page in sorted(document.pages)
    )


def parse(pdf: Path, raw_out: Path, variant: str = "docling") -> ParseResult:
    """Also writes Docling's Markdown next to the raw output, as raw_out with a .md suffix."""
    started = time.monotonic()
    options = PdfPipelineOptions(table_structure_options=VARIANTS[variant])
    converter = DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )
    document = converter.convert(pdf).document
    seconds = time.monotonic() - started
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    document.save_as_json(raw_out)
    raw_out.with_suffix(".md").write_text(page_markdown(document))

    tables = []
    for table in document.tables:
        cells = [
            Cell(
                row=cell.start_row_offset_idx,
                col=cell.start_col_offset_idx,
                text=cell.text,
                col_span=cell.col_span,
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
        parser=variant,
        version=version("docling"),
        seconds=round(seconds, 1),
        page_count=document.num_pages(),
        tables=tables,
        paragraphs=paragraphs,
    )
