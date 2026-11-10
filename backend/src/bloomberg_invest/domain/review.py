"""A person's check of a figure (#19 R4, R9, R10): which figures need one, how a correction is
read, and when a check carries over to a re-extracted figure."""

import re
from collections.abc import Hashable, Iterable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

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


class Verdict(StrEnum):
    accepted = "accepted"
    corrected = "corrected"
    reopened = "reopened"  # undoes the check before it; the figure goes back to CHECKS


def needs_review(
    basis_scope: Scope | str | None, line_item: str, breakdown: str, rules: KpiRules
) -> bool:
    """Only consolidated figures that feed a KPI or screen need a check before they count."""
    return basis_scope == Scope.consolidated and bool(rules.feeds(line_item, breakdown))


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


def numbers_in(paragraph: str) -> list[str]:
    """Each number written in the paragraph, once, in reading order: what a correction of a
    quoted figure can pick. A number is whole, never part of a longer one, as the span check
    reads it."""
    found: list[str] = []
    for m in NUMBER.finditer(paragraph):
        if stands_alone(paragraph, m.start(), m.end()) and m.group() not in found:
            found.append(m.group())
    return found


@dataclass(frozen=True)
class Reading:
    """What a figure read and where: two figures with the same reading read the same value from
    the same source. `source` is the Cell's page, table, row and column (which survive a
    re-parse), or the Span's page, quote and paragraph, or for a figure with no Passage the page
    and the id the LLM cited."""

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
