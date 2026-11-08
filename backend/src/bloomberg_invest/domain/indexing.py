"""What the search indexes see for a Chunk (#21). Pure: no store or model here.

Readers see a Chunk's own text. The full-text and vector indexes see a header first, its
section path and pages, so a short Chunk ("Néant.") still says what it is about. Then each
block: a heading or paragraph as written, a table one line per row with each value after its
column name, so a single figure can match a question.
"""

from bloomberg_invest.domain.chunking import Block, ChunkDraft


def index_text(chunk: ChunkDraft) -> str:
    return f"{header(chunk)}\n" + "\n\n".join(filter(None, map(block_text, chunk.paragraphs)))


def header(chunk: ChunkDraft) -> str:
    first, last = chunk.pages[0], chunk.pages[-1]
    pages = f"p. {first}" if first == last else f"pp. {first}-{last}"
    return f"{' > '.join(chunk.path)} · {pages}" if chunk.path else pages


def block_text(block: Block) -> str:
    return _rows(block) if block.kind == "table" else block.text


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
