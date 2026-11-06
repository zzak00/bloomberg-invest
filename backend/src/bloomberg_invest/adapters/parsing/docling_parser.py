"""Docling with TableFormer v1 in accurate mode, the parser chosen in #10.

Needs the `ingest` extra. Only the ingest CLI imports this module.
"""

import re
from importlib.metadata import version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel, DoclingDocument, TableItem

from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.parsing.outline import Heading, build_outline
from bloomberg_invest.domain.chunking import Block
from bloomberg_invest.domain.model import PageInfo, ParsedDocument

HEADINGS = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
TEXTS = {
    DocItemLabel.TEXT,
    DocItemLabel.PARAGRAPH,
    DocItemLabel.LIST_ITEM,
    DocItemLabel.CAPTION,
    DocItemLabel.FOOTNOTE,
}
# "1)", "a.", "(ii)", "-" or "•" opening a paragraph: a numbered point the chunker may split at.
NUMBERED_POINT = re.compile(r"^(\(?(\d+|[a-z]|[ivx]+)[.)]|[-•–])\s", re.IGNORECASE)


class DoclingParser(Parser):
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

    def read_blocks(self, output: Path) -> list[Block]:
        document = DoclingDocument.load_from_json(output)
        heights = {number: page.size.height for number, page in document.pages.items()}
        blocks = []
        for item, _ in document.iterate_items():
            provs = getattr(item, "prov", None)
            if not provs:
                continue
            boxes = tuple(
                (p.page_no, *_ltrb(p.bbox.to_top_left_origin(page_height=heights[p.page_no])))
                for p in provs
            )
            where = {"page": provs[0].page_no, "boxes": boxes, "last_page": boxes[-1][0]}
            if isinstance(item, TableItem):
                lines = item.export_to_markdown(doc=document).splitlines()
                if len(lines) >= 2:
                    blocks.append(
                        Block(
                            kind="table",
                            text="",
                            header=lines[0],
                            rows=tuple(lines[2:]),
                            columns=item.data.num_cols,
                            **where,
                        )
                    )
            elif item.label in HEADINGS and item.text.strip():
                blocks.append(Block(kind="heading", text=item.text, **where))
            elif item.label in TEXTS and item.text.strip():
                numbered = item.label == DocItemLabel.LIST_ITEM or bool(
                    NUMBERED_POINT.match(item.text)
                )
                blocks.append(Block(kind="text", text=item.text, numbered=numbered, **where))
        return blocks


def _ltrb(box) -> tuple[float, float, float, float]:
    return (box.l, box.t, box.r, box.b)
