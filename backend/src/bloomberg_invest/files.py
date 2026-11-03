"""Where filings and their rendered pages live on disk, keyed by the PDF's SHA-256."""

import os
import tempfile
from datetime import datetime
from pathlib import Path

import pypdfium2 as pdfium

RENDER_SCALE = 2  # 144 dpi: sharp on high-density screens, about 300 KB per page


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
