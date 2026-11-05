"""Chunk a parsed document by its structure (#19 R2). Pure: no parser, store or tokenizer here.

- A table is one Chunk, however long; a table continued at the top of the next page, with the
  same columns and nothing between, is joined to it first.
- A section's paragraphs form one Chunk while they fit the token cap.
- A longer section splits at its numbered points first, otherwise evenly between paragraphs.
- A paragraph is never split, even when it alone is over the cap.

Sections come from the parse; a heading that matches no Section (a chapter heading repeated on
its divider page) keeps the current one, and text before the first heading joins the first.
"""

import math
import re
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import accumulate
from typing import Literal

# (page, left, top, right, bottom) in PDF points, top-left origin.
Box = tuple[int, float, float, float, float]
TokenCount = Callable[[str], int]

NOTE_REFERENCE = re.compile(r"\bnote\s+(\d+)\b", re.IGNORECASE)
NOTE_TITLE = re.compile(r"^NOTE\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Block:
    """One item of the document in reading order: a heading, a text paragraph or a table."""

    kind: Literal["heading", "text", "table"]
    text: str
    page: int
    boxes: tuple[Box, ...] = ()
    last_page: int = 0  # set when the block runs onto later pages
    numbered: bool = False  # a list item or numbered point: "1)", "a.", "-"
    header: str = ""  # tables: the Markdown header row
    rows: tuple[str, ...] = ()  # tables: the Markdown body rows
    columns: int = 0

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(range(self.page, max(self.page, self.last_page) + 1))


@dataclass(frozen=True)
class SectionRef:
    id: str
    title: str
    page: int


@dataclass(frozen=True)
class ChunkDraft:
    index: int
    kind: Literal["text", "table"]
    section_id: str | None
    paragraphs: tuple[Block, ...]
    text: str
    token_count: int
    pages: tuple[int, ...]
    refers_to: tuple[str, ...]  # ids of the NOTE sections the text cites


def chunk(
    blocks: Sequence[Block], sections: Sequence[SectionRef], cap: int, count: TokenCount
) -> list[ChunkDraft]:
    """The document's Chunks in reading order."""
    groups: list[tuple[int, Literal["text", "table"], str | None, list[Block]]] = []
    for section_id, items in _by_section(_join_tables(blocks), sections):
        paragraphs = [(at, b) for at, b in items if b.kind == "text"]
        for part in _split([b for _, b in paragraphs], cap, count):
            first = next(at for at, b in paragraphs if b is part[0])
            groups.append((first, "text", section_id, part))
        for at, b in items:
            if b.kind == "table":
                groups.append((at, "table", section_id, [replace(b, text=_markdown(b))]))

    notes = _note_sections(sections)
    chunks = []
    for index, (_, kind, section_id, part) in enumerate(sorted(groups, key=lambda g: g[0])):
        text = "\n\n".join(b.text for b in part)
        cited = (notes.get(int(n)) for n in NOTE_REFERENCE.findall(text))
        refers_to = tuple(dict.fromkeys(s for s in cited if s and s != section_id))
        chunks.append(
            ChunkDraft(
                index=index,
                kind=kind,
                section_id=section_id,
                paragraphs=tuple(part),
                text=text,
                token_count=count(text),
                pages=tuple(sorted({p for b in part for p in b.pages})),
                refers_to=refers_to,
            )
        )
    return chunks


def _join_tables(blocks: Sequence[Block]) -> list[Block]:
    joined: list[Block] = []
    for block in blocks:
        previous = joined[-1] if joined else None
        if (
            block.kind == "table"
            and previous is not None
            and previous.kind == "table"
            and previous.columns == block.columns
            and block.page == previous.pages[-1] + 1
        ):
            # A repeated header is dropped; a different one is the first row of the continuation.
            rows = block.rows if block.header == previous.header else (block.header, *block.rows)
            joined[-1] = replace(
                previous,
                rows=previous.rows + rows,
                boxes=previous.boxes + block.boxes,
                last_page=block.pages[-1],
            )
        else:
            joined.append(block)
    return joined


def _by_section(
    blocks: Sequence[Block], sections: Sequence[SectionRef]
) -> list[tuple[str | None, list[tuple[int, Block]]]]:
    """Content blocks grouped under their Section, each with its position in reading order."""
    unmatched: dict[tuple[str, int], deque[str]] = defaultdict(deque)
    for s in sections:
        unmatched[(_normal(s.title), s.page)].append(s.id)
    first = sections[0].id if sections else None

    grouped: dict[str | None, list[tuple[int, Block]]] = {}
    current = first
    for at, block in enumerate(blocks):
        if block.kind == "heading":
            ids = unmatched.get((_normal(block.text), block.page))
            if ids:
                current = ids.popleft()
            continue
        grouped.setdefault(current, []).append((at, block))
    return list(grouped.items())


def _split(paragraphs: list[Block], cap: int, count: TokenCount) -> list[list[Block]]:
    if not paragraphs:
        return []
    if _size(paragraphs, count) <= cap:
        return [paragraphs]
    starts = [i for i, p in enumerate(paragraphs) if p.numbered and i > 0]
    if not starts:
        return _even(paragraphs, cap, count)
    segments = [paragraphs[a:b] for a, b in zip([0, *starts], [*starts, len(paragraphs)])]
    parts: list[list[Block]] = []
    current: list[Block] = []
    for segment in segments:
        if current and _size(current + segment, count) > cap:
            parts.append(current)
            current = []
        current = current + segment
    parts.append(current)
    return [p for part in parts for p in _even(part, cap, count)]


def _even(paragraphs: list[Block], cap: int, count: TokenCount) -> list[list[Block]]:
    """The fewest parts under the cap, each cut where the running total is closest to an even
    share."""
    sizes = [count(p.text) for p in paragraphs]
    total, running = sum(sizes), list(accumulate(sizes))
    for n in range(max(1, math.ceil(total / cap)), len(paragraphs) + 1):
        cuts = [0]
        for k in range(1, n):
            # Leave at least one paragraph for each part still to come.
            candidates = range(cuts[-1] + 1, len(paragraphs) - (n - k) + 1)
            cuts.append(min(candidates, key=lambda i: abs(running[i - 1] - total * k / n)))
        parts = [paragraphs[a:b] for a, b in zip(cuts, [*cuts[1:], len(paragraphs)])]
        if all(len(part) == 1 or _size(part, count) <= cap for part in parts):
            return parts
    return [[p] for p in paragraphs]


def _size(paragraphs: list[Block], count: TokenCount) -> int:
    return count("\n\n".join(p.text for p in paragraphs))


def _markdown(table: Block) -> str:
    separator = "| " + " | ".join(["---"] * table.columns) + " |"
    return "\n".join([table.header, separator, *table.rows])


def _note_sections(sections: Sequence[SectionRef]) -> dict[int, str]:
    notes: dict[int, str] = {}
    for s in sections:
        if match := NOTE_TITLE.match(s.title):
            notes.setdefault(int(match.group(1)), s.id)
    return notes


def _normal(title: str) -> str:
    return " ".join(title.split())
