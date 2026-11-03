"""Build the section tree from a flat list of headings.

Docling reports every heading at level 1, so depth comes from the heading's own numbering:

- a chapter is a top-level number ("3. COMPTES CONSOLIDÉS ..."), and each next chapter is the
  previous one plus one;
- "NOTE 13. ..." sits under its chapter;
- inside a note, numbers starting with the note's own number ("13.2") or continuing the note's
  own top-level sequence ("1.", "2." ... in NOTE 1) are the note's subsections; a top-level
  number that breaks that sequence and continues the chapters ("4." after NOTE 34) is a chapter;
- an unnumbered heading hangs under the last numbered heading, beside its unnumbered siblings;
- a chapter heading repeated on the next page (the divider page, then the content) is dropped.
"""

import re
from dataclasses import dataclass, field

from bloomberg_invest.domain import Bbox, SectionNode

# "1.1 Titre", "2.2.1. Titre" or "4. TITRE"; a bare number without its dot ("2025 Rapport") is text.
NUMBERED = re.compile(r"^(\d+(?:\.\d+)+\.?|\d+\.)\s+\S")
NOTE = re.compile(r"^NOTE\s+(\d+)\b", re.IGNORECASE)


@dataclass(frozen=True)
class Heading:
    title: str
    page: int
    bbox: Bbox | None


@dataclass
class _Open:
    node: SectionNode
    depth: int
    numbered: bool


@dataclass
class _Context:
    chapter: int = 0
    note: int | None = None
    note_top: int = 0  # the last top-level number used inside the current note
    stack: list[_Open] = field(default_factory=list)


def build_outline(headings: list[Heading]) -> list[SectionNode]:
    roots: list[SectionNode] = []
    ctx = _Context()
    for heading in headings:
        title = " ".join(heading.title.split())
        depth = _place(title, ctx)
        if depth is None:
            continue
        numbered = depth > 0
        if not numbered:
            parent = next((o for o in reversed(ctx.stack) if o.numbered), None)
            depth = parent.depth + 1 if parent else 1
        while ctx.stack and ctx.stack[-1].depth >= depth:
            ctx.stack.pop()
        node = SectionNode(title=title, level=depth, page=heading.page, bbox=heading.bbox)
        (ctx.stack[-1].node.children if ctx.stack else roots).append(node)
        ctx.stack.append(_Open(node, depth, numbered))
    return roots


def _place(title: str, ctx: _Context) -> int | None:
    """Where the heading goes: its depth (0 when unnumbered, None when it repeats the open chapter).

    Moves ctx to this heading's chapter or note.
    """
    if note := NOTE.match(title):
        ctx.note, ctx.note_top = int(note.group(1)), 0
        return 2
    match = NUMBERED.match(title)
    if not match:
        return 0
    parts = [int(p) for p in match.group(1).rstrip(".").split(".")]
    if ctx.note is not None:
        if parts[0] == ctx.note and len(parts) > 1:
            return 2 + len(parts) - 1
        if len(parts) > 1 or parts[0] == ctx.note_top + 1 or parts[0] != ctx.chapter + 1:
            if len(parts) == 1:
                ctx.note_top = parts[0]
            return 2 + len(parts)
        ctx.note = None
    if len(parts) == 1:
        if parts[0] == ctx.chapter and ctx.stack and _same(ctx.stack[0].node.title, title):
            return None
        ctx.chapter = parts[0]
    return len(parts)


def _same(a: str, b: str) -> bool:
    return a.casefold() == b.casefold()
