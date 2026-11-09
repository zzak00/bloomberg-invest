"""Page furniture Docling read as body text.

Docling labels most running headers and footers `page_header` or `page_footer`, and those never
reach a Chunk. On some pages (image dividers, the back cover) it reads the same footer as text,
which then matches every query naming the company. A text item is furniture when it sits inside
the strip of a labelled header or footer and either repeats a labelled text, page number aside,
or is a bare page number.
"""

import re
import unicodedata
from collections.abc import Iterable

TOLERANCE = 2.0  # points: the same footer drifts by a point or so from page to page


class Furniture:
    def __init__(self, labelled: Iterable[tuple[str, float, float]]) -> None:
        """`labelled`: each labelled header or footer as (text, top, bottom), top-left origin."""
        items = list(labelled)
        self._texts = {key for text, _, _ in items if (key := _words(text))}
        self._strips = [(top - TOLERANCE, bottom + TOLERANCE) for _, top, bottom in items]

    def covers(self, text: str, top: float, bottom: float) -> bool:
        in_strip = any(low <= top and bottom <= high for low, high in self._strips)
        return in_strip and (text.strip().isdigit() or _words(text) in self._texts)


def _words(text: str) -> str:
    """Lower case, accents, digits and punctuation dropped: "90 Maroc Telecom · Rapport" and
    "Maroc Telecom • Rapport" give the same key."""
    plain = unicodedata.normalize("NFKD", text.lower())
    plain = "".join(ch for ch in plain if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[^\W\d_]+", plain))
