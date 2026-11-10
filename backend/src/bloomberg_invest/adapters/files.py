"""Where filings and their rendered pages live on disk, keyed by the PDF's SHA-256."""

import os
import tempfile
from collections.abc import Iterator, Sequence
from datetime import datetime
from math import hypot
from pathlib import Path

import pypdfium2 as pdfium

from bloomberg_invest.domain.chunking import Box
from bloomberg_invest.domain.figures import SPACES, stands_alone

RENDER_SCALE = 2  # 144 dpi: sharp on high-density screens, about 300 KB per page
TOLERANCE = 2.0  # points a quote's centre may sit outside its paragraph's box
CONTEXT = 8  # characters read on each side of a match to tell a whole number from part of one

# A value quoted on a page, and the boxes of the paragraph it must be inside.
Quote = tuple[int, str, Sequence[Box]]


class DocumentFiles:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir

    def pdf_path(self, sha256: str) -> Path:
        return self.data_dir / "documents" / f"{sha256}.pdf"

    def page_png(self, sha256: str, number: int) -> Path:
        return self.data_dir / "pages" / sha256 / f"{number}.png"

    def parse_output(self, sha256: str, started_at: datetime, tool: str) -> str:
        """Where a parse saves the tool's full output, relative to the data directory."""
        return f"parses/{sha256}/{started_at:%Y%m%dT%H%M%SZ}-{tool}.json"

    def render_page(self, sha256: str, number: int) -> Path:
        """The page as a PNG, rendered from the stored PDF on first request."""
        out = self.page_png(sha256, number)
        if not out.exists():
            out.parent.mkdir(parents=True, exist_ok=True)
            pdf = pdfium.PdfDocument(self.pdf_path(sha256))
            try:
                image = pdf[number - 1].render(scale=RENDER_SCALE).to_pil()
            finally:
                pdf.close()
            # A unique temporary file, so two requests for the same page never write one file.
            fd, tmp = tempfile.mkstemp(dir=out.parent, suffix=".png.tmp")
            with os.fdopen(fd, "wb") as handle:
                image.save(handle, format="PNG")
            Path(tmp).replace(out)
        return out

    def quote_near(
        self,
        sha256: str,
        page: int,
        quote: str,
        near: Sequence[Box],
        occurrence: int | None = None,
    ) -> tuple[Box, ...] | None:
        """The quote's boxes in the page's text layer, near `near` (its paragraph's boxes).

        A paragraph that writes the quote more than once says which `occurrence`, from 0 in the
        page's text order: its boxes inside `near`, or None when the text layer does not hold
        that many there, so a number is never boxed where it was not picked. A paragraph that
        writes it once passes None: the place inside `near`, else the nearest, else with nothing
        near the first. None when the text layer lacks the quote."""
        pdf = pdfium.PdfDocument(self.pdf_path(sha256))
        try:
            found = list(_matches(pdf, page, quote))
        finally:
            pdf.close()
        inside = [boxes for boxes in found if near and _all_inside(boxes, near)]
        if occurrence is not None:
            return inside[occurrence] if occurrence < len(inside) else None
        if inside:
            return inside[0]
        return min(found, key=lambda boxes: _distance(boxes, near), default=None)

    def quote_boxes(self, sha256: str, quotes: Sequence[Quote]) -> list[tuple[Box, ...] | None]:
        """Each quote's boxes in the PDF's text layer, one per line, in PDF points from the top
        left; None when the page has no such text inside the paragraph. The PDF is opened once:
        pdfium is not thread-safe, so callers look quotes up from one thread."""
        pdf = pdfium.PdfDocument(self.pdf_path(sha256))
        try:
            return [_find(pdf, page, quote, within) for page, quote, within in quotes]
        finally:
            pdf.close()


def _find(
    pdf: pdfium.PdfDocument, page: int, quote: str, within: Sequence[Box]
) -> tuple[Box, ...] | None:
    return next((boxes for boxes in _matches(pdf, page, quote) if _all_inside(boxes, within)), None)


def _matches(pdf: pdfium.PdfDocument, page: int, quote: str) -> Iterator[tuple[Box, ...]]:
    """The boxes of each place the page's text layer holds the quote as a whole number."""
    if not quote.strip() or not 1 <= page <= len(pdf):
        return
    pdf_page = pdf[page - 1]
    height = pdf_page.get_height()
    text = pdf_page.get_textpage()
    searcher = text.search(quote, match_case=True)
    while found := searcher.get_next():
        start, count = found
        before = text.get_text_range(max(0, start - CONTEXT), min(CONTEXT, start))
        around = SPACES.sub(" ", before + quote + text.get_text_range(start + count, CONTEXT))
        if not stands_alone(around, len(before), len(before) + len(quote)):
            continue
        chars = [text.get_charbox(i) for i in range(start, start + count)]
        # pdfium measures from the bottom left; the viewer and Docling from the top left.
        boxes = _lines(
            [(left, height - top, right, height - bottom) for left, bottom, right, top in chars],
            page,
        )
        if boxes:
            yield boxes


def _all_inside(boxes: Sequence[Box], within: Sequence[Box]) -> bool:
    return all(_inside(box, within) for box in boxes)


def _distance(boxes: Sequence[Box], near: Sequence[Box]) -> float:
    """How far apart the first boxes' centres are, in points; nothing is near no boxes."""
    if not near:
        return 0.0
    (_, l1, t1, r1, b1), (_, l2, t2, r2, b2) = boxes[0], near[0]
    return hypot((l1 + r1 - l2 - r2) / 2, (t1 + b1 - t2 - b2) / 2)


def _lines(chars: list[tuple[float, float, float, float]], page: int) -> tuple[Box, ...]:
    """Character boxes merged into one box per line; spaces have no area and are skipped."""
    lines: list[list[float]] = []
    for left, top, right, bottom in chars:
        if right <= left or bottom <= top:
            continue
        line = next((b for b in lines if top < b[3] and bottom > b[1]), None)
        if line is None:
            lines.append([left, top, right, bottom])
        else:
            line[:] = [
                min(line[0], left),
                min(line[1], top),
                max(line[2], right),
                max(line[3], bottom),
            ]
    return tuple((page, *line) for line in lines)


def _inside(box: Box, within: Sequence[Box]) -> bool:
    page, left, top, right, bottom = box
    x, y = (left + right) / 2, (top + bottom) / 2
    return any(
        on == page
        and edge_left - TOLERANCE <= x <= edge_right + TOLERANCE
        and edge_top - TOLERANCE <= y <= edge_bottom + TOLERANCE
        for on, edge_left, edge_top, edge_right, edge_bottom in within
    )
