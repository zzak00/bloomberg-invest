"""Parse a PDF with PaddleOCR PP-StructureV3, locally, into the parser-neutral format.

PP-StructureV3 OCRs rendered page images; it does not read the PDF's text layer. Tables come back
as HTML (`pred_html`) plus a list of cell boxes (`cell_box_list`) whose order is not documented, so
cells are built from the HTML and the boxes are kept only in the raw output.

It is slow on CPU (about a minute per page on an Apple Silicon Mac), so `pages` can limit the run
to the pages being scored.
"""

import io
import json
import os
import time
from html.parser import HTMLParser
from importlib.metadata import version
from pathlib import Path

import pypdfium2

from bakeoff.tables import Cell, Paragraph, ParseResult, Table

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


class TableHtml(HTMLParser):
    """Cells of an HTML table, placed on a grid that accounts for rowspan and colspan."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: list[Cell] = []
        self.taken: set[tuple[int, int]] = set()
        self.row, self.col, self.in_head = -1, 0, False
        self.current: dict | None = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "thead":
            self.in_head = True
        elif tag == "tr":
            self.row, self.col = self.row + 1, 0
        elif tag in ("td", "th"):
            while (self.row, self.col) in self.taken:
                self.col += 1
            self.current = {
                "row": self.row,
                "col": self.col,
                "rows": int(attrs.get("rowspan") or 1),
                "cols": int(attrs.get("colspan") or 1),
                "text": "",
                "head": self.in_head or tag == "th",
            }

    def handle_data(self, data):
        if self.current is not None:
            self.current["text"] += data

    def handle_endtag(self, tag):
        if tag == "thead":
            self.in_head = False
        elif tag in ("td", "th") and self.current is not None:
            c = self.current
            for r in range(c["row"], c["row"] + c["rows"]):
                for k in range(c["col"], c["col"] + c["cols"]):
                    self.taken.add((r, k))
            self.cells.append(
                Cell(
                    row=c["row"],
                    col=c["col"],
                    text=" ".join(c["text"].split()),
                    kind="column_header" if c["head"] else "content",
                    col_span=c["cols"],
                )
            )
            self.col += c["cols"]
            self.current = None


def cells_from_html(html: str) -> list[Cell]:
    parser = TableHtml()
    parser.feed(html)
    return parser.cells


def selected_pages(pdf: Path, pages: list[int] | None) -> tuple[list[int], bytes]:
    """The 1-based page numbers to parse, and a PDF holding only those pages."""
    source = pypdfium2.PdfDocument(pdf)
    numbers = pages or list(range(1, len(source) + 1))
    part = pypdfium2.PdfDocument.new()
    part.import_pages(source, [n - 1 for n in numbers])
    buffer = io.BytesIO()
    part.save(buffer)
    return numbers, buffer.getvalue()


def parse(pdf: Path, raw_out: Path, pages: list[int] | None = None) -> ParseResult:
    """Also writes PaddleOCR's Markdown next to the raw output, as raw_out with a .md suffix."""
    from paddleocr import PPStructureV3

    numbers, body = selected_pages(pdf, pages)
    raw_out.parent.mkdir(parents=True, exist_ok=True)
    subset = raw_out.with_suffix(".input.pdf")
    subset.write_bytes(body)

    pipeline = PPStructureV3(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        use_formula_recognition=False,
        use_seal_recognition=False,
        use_chart_recognition=False,
    )
    tables, paragraphs, raw, markdown = [], [], [], ""
    started = time.monotonic()
    for result in pipeline.predict(str(subset)):
        res = result.json["res"]
        page = numbers[res["page_index"] or 0]
        raw.append({"page": page, "result": res})
        markdown += f"<!-- page {page} -->\n{result.markdown['markdown_texts']}\n\n"
        for table in res.get("table_res_list", []):
            tables.append(Table([page], "", cells_from_html(table["pred_html"])))
        paragraphs += [
            Paragraph(page, block["block_content"])
            for block in res.get("parsing_res_list", [])
            if block["block_label"] != "table" and block["block_content"].strip()
        ]
    seconds = time.monotonic() - started
    subset.unlink()
    raw_out.write_text(json.dumps(raw, ensure_ascii=False, default=str))
    raw_out.with_suffix(".md").write_text(markdown)

    return ParseResult(
        parser="paddle-structurev3",
        version=f"paddleocr {version('paddleocr')} paddle {version('paddlepaddle')}",
        seconds=round(seconds, 1),
        page_count=len(numbers),
        tables=tables,
        paragraphs=paragraphs,
    )
