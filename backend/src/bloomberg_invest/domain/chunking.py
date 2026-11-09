"""Chunk a parsed document by its structure (#19 R2). Pure: no parser, store or tokenizer here.

- A table is its own Chunk; a table continued at the top of the next page, with the same columns
  and nothing between, is joined to it first. A table longer than its cap, read as search reads
  it (one line per row), splits evenly between rows; every part repeats the column header and
  the headings above it, and keeps only the pages and boxes of its own rows.
- A section's paragraphs form one Chunk while they fit the token cap.
- A longer section splits at its numbered points first, otherwise evenly between paragraphs.
- A paragraph is never split, even when it alone is over the cap.
- A heading starts the Chunk of the content after it, so no text is lost when Docling takes a
  sentence for a heading; a heading with no content of its own joins the next Chunk.

Sections come from the parse; a heading that matches no Section (a chapter heading repeated on
its divider page) keeps the current one, and text before the first heading joins the first. A
heading that only repeats the current Section's title, as after a page break, is dropped.
"""

import math
import re
from collections import defaultdict, deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from itertools import accumulate
from typing import Literal

from bloomberg_invest.domain import tables as table_text

# (page, left, top, right, bottom) in PDF points, top-left origin.
Box = tuple[int, float, float, float, float]
TokenCount = Callable[[str], int]

NOTE_REFERENCE = re.compile(r"\bnote\s+(\d+)\b", re.IGNORECASE)
NOTE_TITLE = re.compile(r"^NOTE\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Block:
    """One item of the document in reading order: a heading, a text paragraph or a table. The
    chunker never splits one; Blocks are not stored on their own (ADR 0004)."""

    kind: Literal["heading", "text", "table"]
    text: str
    page: int
    boxes: tuple[Box, ...] = ()
    last_page: int = 0  # set when the block runs onto later pages
    numbered: bool = False  # a list item or numbered point: "1)", "a.", "-"
    header: str = ""  # tables: the Markdown header row
    rows: tuple[str, ...] = ()  # tables: the Markdown body rows
    row_pages: tuple[int, ...] = ()  # tables joined across pages: each row's page
    columns: int = 0

    @property
    def pages_of_rows(self) -> tuple[int, ...]:
        return self.row_pages or (self.page,) * len(self.rows)

    @property
    def pages(self) -> tuple[int, ...]:
        return tuple(range(self.page, max(self.page, self.last_page) + 1))


@dataclass(frozen=True)
class Caps:
    """Token caps: a section's text Chunk, and a table read one line per row."""

    text: int
    table: int


@dataclass(frozen=True)
class SectionRef:
    id: str
    title: str
    page: int
    parent: str | None = None  # the id of the Section it sits in


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
    path: tuple[str, ...] = ()  # titles of its Section and the Sections above, outermost first
    table: int | None = None  # tables: shared by the parts of one table
    part: int = 0  # tables: this part's number, from 1
    parts: int = 0  # tables: how many parts the table has


# Where a Chunk sits in reading order, its kind, Section and blocks, and for a table part the
# table's reading position, the part number and the number of parts.
Group = tuple[int, Literal["text", "table"], str | None, list[Block], tuple[int, int, int] | None]


def chunk(
    blocks: Sequence[Block], sections: Sequence[SectionRef], caps: Caps, count: TokenCount
) -> list[ChunkDraft]:
    """The document's Chunks in reading order."""
    groups: list[Group] = []
    for section_id, items in _by_section(_join_tables(blocks), sections):
        texts: list[tuple[int, Block]] = []
        tables: list[list[tuple[int, Block]]] = []
        headings: list[tuple[int, Block]] = []
        for at, b in items:
            if b.kind == "heading":
                headings.append((at, b))
            elif b.kind == "text":
                texts += [*headings, (at, b)]
                headings = []
            else:
                tables.append([*headings, (at, b)])
                headings = []
        texts += headings  # the document's last headings, with nothing after them
        for part in _split([b for _, b in texts], caps.text, count):
            first = next(at for at, b in texts if b is part[0])
            groups.append((first, "text", section_id, part, None))
        for table in tables:
            at, (*heads, block) = table[0][0], [b for _, b in table]
            parts = _split_table(block, caps.table, count)
            for n, part in enumerate(parts, 1):
                part = replace(part, text=_markdown(part))
                # Later parts repeat the headings as context: their text, not their place.
                context = heads if n == 1 else [replace(h, boxes=(), page=part.page) for h in heads]
                groups.append((at, "table", section_id, [*context, part], (at, n, len(parts))))

    notes = _note_sections(sections)
    paths = _paths(sections)
    chunks = []
    # Sorting is stable, so a table's parts keep their order.
    for index, (_, kind, section_id, part, of_table) in enumerate(
        sorted(groups, key=lambda g: g[0])
    ):
        text = "\n\n".join(b.text for b in part)
        body = "\n\n".join(b.text for b in part if b.kind != "heading")
        cited = (notes.get(int(n)) for n in NOTE_REFERENCE.findall(body))
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
                path=paths.get(section_id, ()),
                **(dict(zip(("table", "part", "parts"), of_table)) if of_table else {}),
            )
        )
    return chunks


def _paths(sections: Sequence[SectionRef]) -> dict[str | None, tuple[str, ...]]:
    """Each Section's title path, outermost first; parents come before their children."""
    paths: dict[str | None, tuple[str, ...]] = {}
    for s in sections:
        paths[s.id] = (*paths.get(s.parent, ()), s.title) if s.parent else (s.title,)
    return paths


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
                row_pages=previous.pages_of_rows + (block.page,) * len(rows),
                boxes=previous.boxes + block.boxes,
                last_page=block.pages[-1],
            )
        else:
            joined.append(block)
    return joined


def _by_section(
    blocks: Sequence[Block], sections: Sequence[SectionRef]
) -> list[tuple[str | None, list[tuple[int, Block]]]]:
    """Blocks grouped under their Section, each with its position in reading order. Headings go
    with the content after them, in that content's Section."""
    unmatched: dict[tuple[str, int], deque[str]] = defaultdict(deque)
    for s in sections:
        unmatched[(_normal(s.title), s.page)].append(s.id)
    titles = {s.id: _normal(s.title) for s in sections}
    first = sections[0].id if sections else None

    grouped: dict[str | None, list[tuple[int, Block]]] = {}
    current = first
    headings: list[tuple[int, Block]] = []
    for at, block in enumerate(blocks):
        if block.kind == "heading":
            ids = unmatched.get((_normal(block.text), block.page))
            if ids:
                current = ids.popleft()
            elif _normal(block.text) == titles.get(current):
                continue
            headings.append((at, block))
            continue
        grouped.setdefault(current, []).extend([*headings, (at, block)])
        headings = []
    if headings:
        grouped.setdefault(current, []).extend(headings)
    return list(grouped.items())


def _split(paragraphs: list[Block], cap: int, count: TokenCount) -> list[list[Block]]:
    if not paragraphs:
        return []
    if _size(paragraphs, count) <= cap:
        return [paragraphs]
    starts = [i for i, p in enumerate(paragraphs) if (p.numbered or p.kind == "heading") and i > 0]
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
    cuts = _even_cuts(
        [count(p.text) for p in paragraphs],
        lambda a, b: b - a == 1 or _size(paragraphs[a:b], count) <= cap,
        cap,
    )
    return [paragraphs[a:b] for a, b in cuts]


def _split_table(table: Block, cap: int, count: TokenCount) -> list[Block]:
    """The table in the fewest parts whose lines fit the cap, cut between rows; a row over the
    cap is a part of its own."""
    head = table_text.corner(table.header)
    lines = table_text.row_lines(table.header, table.rows)

    def size(a: int, b: int) -> int:
        return count("\n".join([head, *lines[a:b]]))

    if not lines or size(0, len(lines)) <= cap:
        return [table]
    cuts = _even_cuts(
        [count(line) for line in lines], lambda a, b: b - a == 1 or size(a, b) <= cap, cap
    )
    pages = table.pages_of_rows
    parts = []
    for a, b in cuts:
        on = tuple(sorted(set(pages[a:b])))
        parts.append(
            replace(
                table,
                rows=table.rows[a:b],
                row_pages=pages[a:b],
                page=on[0],
                last_page=on[-1] if len(on) > 1 else 0,
                boxes=tuple(box for box in table.boxes if box[0] in on),
            )
        )
    return parts


def _even_cuts(
    sizes: list[int], fits: Callable[[int, int], bool], cap: int
) -> list[tuple[int, int]]:
    """Cut `sizes` into the fewest runs that fit, each cut where the running total is closest to
    an even share; as a last resort, one item per run."""
    total, running = sum(sizes), list(accumulate(sizes))
    for n in range(max(1, math.ceil(total / cap)), len(sizes) + 1):
        cuts = [0]
        for k in range(1, n):
            # Leave at least one item for each run still to come.
            candidates = range(cuts[-1] + 1, len(sizes) - (n - k) + 1)
            cuts.append(min(candidates, key=lambda i: abs(running[i - 1] - total * k / n)))
        runs = list(zip(cuts, [*cuts[1:], len(sizes)]))
        if all(fits(a, b) for a, b in runs):
            return runs
    return [(i, i + 1) for i in range(len(sizes))]


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
