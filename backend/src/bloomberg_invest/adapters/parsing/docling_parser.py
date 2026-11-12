"""Docling with TableFormer v1 in accurate mode, the parser chosen in #10.

Needs the `ingest` extra. Only the ingest CLI imports this module.
"""

import re
from importlib.metadata import version
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    PdfPipelineOptions,
    RapidOcrOptions,
    TableFormerMode,
    TableStructureOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling_core.types.doc import DocItemLabel, DoclingDocument, TableItem

from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.parsing.furniture import Furniture
from bloomberg_invest.adapters.parsing.outline import Heading, build_outline
from bloomberg_invest.domain.chunking import Block
from bloomberg_invest.domain.model import PageInfo, ParsedDocument, ParsedTable, TableCell

HEADINGS = {DocItemLabel.TITLE, DocItemLabel.SECTION_HEADER}
TEXTS = {
    DocItemLabel.TEXT,
    DocItemLabel.PARAGRAPH,
    DocItemLabel.LIST_ITEM,
    DocItemLabel.CAPTION,
    DocItemLabel.FOOTNOTE,
    # Docling can take a page of prose for code (golden p. 16); its text still belongs in Chunks.
    DocItemLabel.CODE,
}
FURNITURE = {DocItemLabel.PAGE_HEADER, DocItemLabel.PAGE_FOOTER}
# "1)", "a.", "(ii)", "-" or "•" opening a paragraph: a numbered point the chunker may split at.
NUMBERED_POINT = re.compile(r"^(\(?(\d+|[a-z]|[ivx]+)[.)]|[-•–])\s", re.IGNORECASE)
# RapidOCR keeps its models in its own install folder unless told otherwise, so every new
# .venv or container downloaded them again from modelscope.cn (#47). Next to Hugging Face's
# cache, they are shared by worktrees, the `models` volume in compose and the CI cache.
OCR_MODELS = Path.home() / ".cache" / "rapidocr"


class DoclingParser(Parser):
    tool = "docling"

    def __init__(self) -> None:
        self.tool_version = version("docling")
        # Accurate is Docling's default today; set it so a new default can't change it silently.
        self._table_options = TableStructureOptions(
            mode=TableFormerMode.ACCURATE, do_cell_matching=True
        )
        # The engine Docling's automatic choice picks with the ingest extra installed (RapidOCR
        # on torch, its default language), named so its model folder can be set.
        self._ocr_options = RapidOcrOptions(
            backend="torch",
            lang=[],
            rapidocr_params={"Global.model_root_dir": str(OCR_MODELS)},
        )
        self.config = {
            "table_structure": "TableFormer v1",
            "mode": self._table_options.mode.value,
            "do_cell_matching": str(self._table_options.do_cell_matching).lower(),
            "ocr": f"rapidocr {self._ocr_options.backend}",
        }

    def parse(self, pdf: Path, output: Path) -> ParsedDocument:
        options = PdfPipelineOptions(
            table_structure_options=self._table_options, ocr_options=self._ocr_options
        )
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
        )
        document = converter.convert(pdf).document
        output.parent.mkdir(parents=True, exist_ok=True)
        document.save_as_json(output)
        return self.read_parsed(output)

    def read_parsed(self, output: Path) -> ParsedDocument:
        """Read a saved output back as pages, outline and tables, as `parse` returns them."""
        document = DoclingDocument.load_from_json(output)
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
        heights = {number: page.height for number, page in pages.items()}
        return ParsedDocument(
            pages=[pages[n] for n in sorted(pages)],
            sections=build_outline(headings),
            tables=[_table(t, heights) for t in document.tables if t.prov],
        )

    def read_blocks(self, output: Path) -> list[Block]:
        document = DoclingDocument.load_from_json(output)
        heights = {number: page.size.height for number, page in document.pages.items()}
        furniture = Furniture(
            (item.text, *_top_bottom(item.prov[0], heights))
            for item in document.texts
            if item.label in FURNITURE and item.prov
        )
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
                if furniture.covers(item.text, *_top_bottom(provs[0], heights)):
                    continue
                numbered = item.label == DocItemLabel.LIST_ITEM or bool(
                    NUMBERED_POINT.match(item.text)
                )
                blocks.append(Block(kind="text", text=item.text, numbered=numbered, **where))
        return blocks


def _table(table: TableItem, heights: dict[int, float]) -> ParsedTable:
    """A table and its cells, each cell on the page whose part of the table holds it."""
    parts = [
        (p.page_no, p.bbox.to_top_left_origin(page_height=heights[p.page_no])) for p in table.prov
    ]

    def page_of(box) -> int:
        x, y = (box.l + box.r) / 2, (box.t + box.b) / 2
        inside = (n for n, b in parts if b.l <= x <= b.r and b.t <= y <= b.b)
        return next(inside, parts[0][0])

    cells = []
    for cell in table.data.table_cells:
        if cell.bbox is None:
            continue
        page = parts[0][0] if len(parts) == 1 else page_of(cell.bbox)
        box = cell.bbox.to_top_left_origin(page_height=heights[page])
        cells.append(
            TableCell(
                row=cell.start_row_offset_idx,
                col=cell.start_col_offset_idx,
                row_span=cell.row_span,
                col_span=cell.col_span,
                text=cell.text,
                page=page,
                bbox=_ltrb(box),
                column_header=cell.column_header,
                row_header=cell.row_header,
            )
        )
    page, box = parts[0]
    return ParsedTable(page=page, bbox=_ltrb(box), cells=cells)


def _ltrb(box) -> tuple[float, float, float, float]:
    return (box.l, box.t, box.r, box.b)


def _top_bottom(prov, heights) -> tuple[float, float]:
    box = prov.bbox.to_top_left_origin(page_height=heights[prov.page_no])
    return box.t, box.b
