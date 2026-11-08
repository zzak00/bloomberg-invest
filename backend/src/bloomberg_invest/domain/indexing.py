"""What the search indexes see for a Paragraph (#21 R2). Pure: no store or model here.

Readers see a Paragraph's own text. The full-text and vector indexes see its section path and
page first, so a short paragraph ("Néant.") still says what it is about, and a table as one line
per row with each value after its column name, so a single figure can match a question.
A heading is not searched on its own: its title already leads the Paragraphs under it.
"""

from collections.abc import Sequence

from bloomberg_invest.domain.chunking import Block


def is_search_unit(block: Block) -> bool:
    return block.kind != "heading"


def index_text(block: Block, path: Sequence[str]) -> str:
    """`path`: the titles of the Paragraph's Section and the Sections above it, outermost first."""
    where = " > ".join(path)
    head = f"{where} · p. {block.page}" if where else f"p. {block.page}"
    body = _rows(block) if block.kind == "table" else block.text
    return f"{head}\n{body}" if body else head


def _rows(table: Block) -> str:
    # The top-left cell names the label column or gives the unit, "(En millions de MAD)".
    corner, *columns = _cells(table.header)
    lines = [corner] if corner else []
    for row in table.rows:
        label, *values = _cells(row)
        pairs = [
            f"{column} {value}" if column else value
            for column, value in zip(columns, values)
            if value
        ]
        line = " · ".join(pairs)
        if label:
            line = f"{label}: {line}" if line else label
        if line:
            lines.append(line)
    return "\n".join(lines)


def _cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
