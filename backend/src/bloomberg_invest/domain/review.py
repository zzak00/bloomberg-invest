"""A person's check of a figure (#19 R4, R9, R10): which figures need one, how a correction is
read, and when a check carries over to a re-extracted figure."""

import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from bloomberg_invest.domain.chunking import Box
from bloomberg_invest.domain.figures import (
    Scope,
    parse_unit,
    parse_value,
    scaled,
    stands_alone,
)
from bloomberg_invest.domain.kpis import KpiRules

# A number as filings write it: `36 681`, `1 284,6`, `4,01`, `2025`, `-988`. Groups of three
# after a space join one number; anything else starts another (`36 699 36 681` is two).
NUMBER = re.compile(r"[-−]?(?:\d{1,3}(?:[  ]\d{3})+|\d+)(?:,\d+)?")
CONTEXT = 32  # characters shown on each side of a number a correction can pick


class Verdict(StrEnum):
    accepted = "accepted"
    corrected = "corrected"
    reopened = "reopened"  # undoes the check before it; the figure goes back to CHECKS

    @property
    def in_force(self) -> bool:
        """A figure's latest check is in force unless it reopened the figure."""
        return self is not Verdict.reopened


class CheckStatus(StrEnum):
    """Where a CHECKS row stands: its figures' check in force, or what they wait for."""

    to_check = "to_check"
    rejected = "rejected"  # the extraction check refused it: it can only be corrected
    accepted = "accepted"
    corrected = "corrected"


class Gated(Protocol):
    """What decides whether a figure needs a check: a Fact, or a rejected figure."""

    @property
    def basis_scope(self) -> Scope | str | None: ...
    @property
    def line_item(self) -> str: ...
    @property
    def breakdown(self) -> str: ...


def needs_check(figure: Gated, rules: KpiRules) -> bool:
    """Only consolidated figures that feed a KPI or screen need a check before they count
    (#19 R10)."""
    return figure.basis_scope == Scope.consolidated and bool(
        rules.feeds(figure.line_item, figure.breakdown)
    )


class InvalidCorrection(ValueError):
    """A corrected value that is not one number, or whose unit names nothing countable."""


@dataclass(frozen=True)
class Correction:
    """The right value, as the person gave it, parsed in Python like an extracted one."""

    value_as_written: str
    unit_as_written: str
    value: str  # exact decimal in the base unit
    unit: str
    scale: int
    currency: str | None


def correction(value_as_written: str, unit_as_written: str) -> Correction:
    value, unit = parse_value(value_as_written), parse_unit(unit_as_written)
    if value is None:
        raise InvalidCorrection(f"{value_as_written!r} is not one number")
    if unit is None:
        raise InvalidCorrection(f"the figure's unit {unit_as_written!r} names nothing countable")
    return Correction(
        value_as_written=value_as_written.strip(),
        unit_as_written=unit_as_written,
        value=scaled(value, unit),
        unit=unit.unit,
        scale=unit.scale,
        currency=unit.currency,
    )


class Checked(Protocol):
    """A check in force on a figure."""

    @property
    def verdict(self) -> Verdict: ...
    @property
    def correction(self) -> Correction | None: ...


def correction_in_force(check: Checked | None) -> Correction | None:
    """The right value a figure's check gives it: a correction's, never an acceptance's. A
    figure with one shows that value, not what was read (#19 R8)."""
    if check is None or check.verdict != Verdict.corrected:
        return None
    return check.correction


@dataclass(frozen=True)
class QuotedSource:
    """A number a correction picked in the figure's paragraph: a new Span the Review cites.
    Its boxes are the number's own, found in the PDF's text layer."""

    page: int
    quote: str
    text: str  # the paragraph
    boxes: tuple[Box, ...]


@dataclass(frozen=True)
class ReviewDraft:
    """A check to record. A correction cites what the person picked: a Cell of the figure's
    table row, a number of its paragraph, or nothing for a typed value."""

    verdict: Verdict
    reviewer: str
    reviewed_at: datetime
    correction: Correction | None = None
    cell_id: str | None = None
    quoted: QuotedSource | None = None

    def __post_init__(self) -> None:
        if (self.verdict == Verdict.corrected) != (self.correction is not None):
            raise ValueError("a correction, and only a correction, carries the right value")
        if self.cell_id is not None and self.quoted is not None:
            raise ValueError("a correction cites one source at most")


@dataclass(frozen=True)
class Number:
    """A number written in a paragraph, and where it starts."""

    text: str
    start: int


def numbers_in(paragraph: str) -> list[Number]:
    """Each number written in the paragraph, in reading order, every time it is written: what a
    correction of a quoted figure can pick. A number is whole, never part of a longer one, as the
    span check reads it."""
    return [
        Number(m.group(), m.start())
        for m in NUMBER.finditer(paragraph)
        if stands_alone(paragraph, m.start(), m.end())
    ]


def occurrence(paragraph: str, number: Number) -> int | None:
    """Which time the number is written in the paragraph, from 0; None when the paragraph does
    not write that number where it says."""
    same = [n.start for n in numbers_in(paragraph) if n.text == number.text]
    return same.index(number.start) if number.start in same else None


def around(paragraph: str, number: Number) -> str:
    """The number with the words around it where it is written, cut at whole words; a side with
    no space to cut at is kept whole."""
    start, end = number.start, number.start + len(number.text)
    before, after = paragraph[max(0, start - CONTEXT) : start], paragraph[end : end + CONTEXT]
    if start > CONTEXT:
        before = "…" + (before[before.index(" ") + 1 :] if " " in before else before)
    if end + CONTEXT < len(paragraph):
        after = (after[: after.rindex(" ")] if " " in after else after) + "…"
    return before + number.text + after


@dataclass(frozen=True)
class Reading:
    """What a figure read and where: two figures with the same reading read the same value from
    the same source. `source` is the Cell's page, table, row and column (which survive a
    re-parse), or the Span's page, quote and paragraph. A figure with no Passage has no reading:
    its check never carries over."""

    line_item: str
    fiscal_year: int
    basis_scope: str | None
    breakdown: str
    value_as_written: str
    unit_as_written: str
    source: tuple[Hashable, ...]


def carried(
    earlier: Iterable[tuple[Reading, str]], later: Iterable[tuple[Reading, str]]
) -> list[tuple[str, str]]:
    """The checks that carry over (#19 R4): (review id, new figure id) for each new figure that
    reads exactly what a checked figure of the previous Run read. `earlier` pairs each checked
    figure's reading with its check in force; `later` each new figure's reading with its id."""
    checks = dict(earlier)
    return [(checks[r], figure_id) for r, figure_id in later if r in checks]
