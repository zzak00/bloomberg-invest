"""What the search indexes see for a Chunk (#21). Pure: no store or model here.

Readers see a Chunk's own text. The vector index sees a header first, its
section path and pages, so a short Chunk ("Néant.") still says what it is about. Then each
block: a heading or paragraph as written, a table one line per row with each value after its
column name, so a single figure can match a question.
"""

from dataclasses import dataclass

from bloomberg_invest.domain import tables
from bloomberg_invest.domain.chunking import Block, ChunkDraft, header_line


@dataclass(frozen=True)
class EmbedInput:
    """A current Chunk and the index text its vector is embedded from."""

    chunk_id: str
    text: str


def index_text(chunk: ChunkDraft) -> str:
    return f"{header(chunk)}\n" + "\n\n".join(filter(None, map(block_text, chunk.paragraphs)))


def header(chunk: ChunkDraft) -> str:
    return header_line(chunk.path, chunk.pages)


def block_text(block: Block) -> str:
    return _rows(block) if block.kind == "table" else block.text


def _rows(table: Block) -> str:
    lines = [tables.corner(table.header), *tables.row_lines(table.header, table.rows)]
    return "\n".join(filter(None, lines))
