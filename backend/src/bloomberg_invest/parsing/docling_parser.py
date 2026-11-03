"""Docling with TableFormer v1 in accurate mode, the parser chosen in #10.

Needs the `ingest` extra. Only the ingest CLI imports this module.
"""

from importlib.metadata import version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel

from bloomberg_invest.domain import PageInfo, ParsedDocument
from bloomberg_invest.parsing.outline import Heading, build_outline

HEADINGS = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}


class DoclingParser:
    tool = "docling"

    def __init__(self) -> None:
        self.tool_version = version("docling")
        # Accurate is Docling's default today; set it so a new default can't change it silently.
        self._table_options = TableStructureOptions(
            mode=TableFormerMode.ACCURATE, do_cell_matching=True
        )
        self.config = {
            "table_structure": "TableFormer v1",
            "mode": self._table_options.mode.value,
            "do_cell_matching": str(self._table_options.do_cell_matching).lower(),
        }

    def parse(self, pdf: Path, output: Path) -> ParsedDocument:
        options = PdfPipelineOptions(table_structure_options=self._table_options)
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        document = converter.convert(pdf).document
        output.parent.mkdir(parents=True, exist_ok=True)
        document.save_as_json(output)

        pages = {
            number: PageInfo(number=number, width=page.size.width, height=page.size.height)
            for number, page in document.pages.items()
        }
        headings = []
        for item, _ in document.iterate_items():
            if item.label not in HEADINGS or not item.prov or not item.text.strip():
                continue
            prov = item.prov[0]
            box = prov.bbox.to_top_left_origin(page_height=pages[prov.page_no].height)
            headings.append(
                Heading(
                    title=item.text,
                    page=prov.page_no,
                    bbox=(box.l, box.t, box.r, box.b),
                )
            )
        return ParsedDocument(
            pages=[pages[n] for n in sorted(pages)], sections=build_outline(headings)
        )
