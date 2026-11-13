"""A person's check of a figure (#19 R4, R9, R10): which figures need one, how a correction is
read, and when a check carries over to a re-extracted figure."""

import re
import uuid
from collections.abc import Hashable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from bloomberg_invest.domain.chunking import Box
from bloomberg_invest.domain.dossier import Stated, agreeing, same_value
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


class Filed(Protocol):
    @property
    def currency(self) -> str: ...


class Gated(Protocol):
    """What decides whether a figure needs a check: a Fact, or a rejected figure."""

    @property
    def basis_scope(self) -> Scope | None: ...
    @property
    def line_item(self) -> str: ...
    @property
    def breakdown(self) -> str: ...
    @property
    def currency(self) -> str | None: ...
    @property
    def document(self) -> Filed: ...


def needs_check(figure: Gated, rules: KpiRules) -> bool:
    """Only consolidated figures that feed a KPI or screen need a check before they count
    (#19 R10), in the currency of their filing's statements, or in none (`%`, `shares`): a
    translation into another currency never counts (#56)."""
    return (
        figure.basis_scope == Scope.consolidated
        and bool(rules.feeds(figure.line_item, figure.breakdown))
        and figure.currency in (None, figure.document.currency)
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

    def stated(self) -> dict[str, str | int | None]:
        """The fields a figure shows its value with, as a correction gives them."""
        return {
            "value_as_written": self.value_as_written,
            "unit_as_written": self.unit_as_written,
            "value": self.value,
            "unit": self.unit,
            "scale": self.scale,
            "currency": self.currency,
        }


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


def correction_in_force[C: Checked](check: C | None) -> tuple[C, Correction] | None:
    """The check that gives a figure its right value, with that value: a correction's, never an
    acceptance's. A figure with one shows that value, not what was read (#19 R8), and a
    rejected figure counts in the dossier only with one."""
    if check is None or check.verdict != Verdict.corrected or check.correction is None:
        return None
    return check, check.correction


class Dated(Protocol):
    @property
    def reviewed_at(self) -> datetime: ...


def check_of[C: Dated](checks: Sequence[C | None]) -> C | None:
    """The check in force on a value from the checks of the figures stating it: the latest, once
    every figure is checked. A re-extract may keep the check of some figures and not others, and
    until a person checks the rest the value is not checked."""
    done = [c for c in checks if c is not None]
    if not done or len(done) != len(checks):
        return None
    return max(done, key=lambda c: c.reviewed_at)


class Filed(Protocol):
    """A figure as D4 reads it: the filing stating it, and its check in force."""

    @property
    def document(self) -> "Identified": ...
    @property
    def review(self) -> Dated | None: ...


def value_check[F: Filed](figures: Sequence[F]) -> Dated | None:
    """The check in force on a value from the figures stating it, of every filing (#24 D4): one
    filing's check covers the value once every figure of that filing stating it is checked
    (`check_of`); the latest such check."""
    documents = dict.fromkeys(f.document.id for f in figures)
    checks = [check_of([f.review for f in figures if f.document.id == d]) for d in documents]
    return max((c for c in checks if c is not None), key=lambda c: c.reviewed_at, default=None)


def covering[C](
    stated: Stated, document_id: str, checked: Iterable[tuple[str, Stated, C]]
) -> C | None:
    """The check of another filing whose value in force this filing's figure states (#24 D4),
    given each checked value with its filing's id and its check; None when there is none."""
    return next(
        (check for d, value, check in checked if d != document_id and same_value(value, stated)),
        None,
    )


_STATUS_OF = {Verdict.accepted: CheckStatus.accepted, Verdict.corrected: CheckStatus.corrected}


def fact_status(check: Checked | None) -> CheckStatus:
    """Where a CHECKS row of Facts stands, from its check in force (never a reopening)."""
    return _STATUS_OF[check.verdict] if check is not None else CheckStatus.to_check


def rejected_status(check: Checked | None) -> CheckStatus:
    """Where a rejected figure's row stands: rejected until a person corrects it."""
    return _STATUS_OF[check.verdict] if check is not None else CheckStatus.rejected


class Identified(Protocol):
    @property
    def id(self) -> str: ...


class Keyed(Gated, Protocol):
    """A figure as a check groups it: a Fact, or a rejected figure."""

    @property
    def document(self) -> Identified: ...
    @property
    def fiscal_year(self) -> int: ...


class KeyedFact(Keyed, Stated, Protocol):
    @property
    def unit(self) -> str: ...
    @property
    def currency(self) -> str | None: ...


@dataclass(frozen=True)
class CheckKey:
    """What one check covers: a line item, or one breakdown of it, in one fiscal year, on one
    basis and in one currency, as one filing states it."""

    document_id: str
    line_item: str
    fiscal_year: int
    basis_scope: Scope | None
    breakdown: str
    currency: str  # a Fact's currency, or its unit when it has none (`%`, `shares`)


def across_filings(key: CheckKey) -> CheckKey:
    """The key of a value as every filing states it: D4 compares values across filings."""
    return replace(key, document_id="")


def fact_key(fact: KeyedFact) -> CheckKey:
    """A Fact's key, in its parsed currency (or its unit when it has none)."""
    return _key(fact, fact.currency or fact.unit)


def rejected_key(figure: Keyed) -> CheckKey:
    """A rejected figure's key. It has no parsed currency, and its empty one keeps it from
    sharing a key, and so a check, with any Fact: it is checked on its own. Two functions, not
    one, so no key is guessed from which fields a figure has."""
    return _key(figure, "")


def _key(figure: Keyed, currency: str) -> CheckKey:
    return CheckKey(
        figure.document.id,
        figure.line_item,
        figure.fiscal_year,
        figure.basis_scope,
        figure.breakdown,
        currency,
    )


def refusal(
    facts: Sequence[KeyedFact], rejected: Sequence[Keyed], verdict: Verdict, rules: KpiRules
) -> str | None:
    """Why a check of these figures, one CHECKS row's, is refused; None when it fits them."""
    figures: list[Keyed] = [*facts, *rejected]
    if not figures:
        return "A check names the figures it covers"
    if not all(needs_check(f, rules) for f in figures):
        return "A figure that feeds no KPI or screen needs no check"
    if len({fact_key(f) for f in facts} | {rejected_key(r) for r in rejected}) > 1:
        return "One check covers one line item, year, basis and currency of one filing"
    if rejected and len(figures) > 1:
        return "A rejected figure is checked on its own"
    if len(agreeing(facts)) > 1:
        return "These figures state different values: check each value on its own"
    if rejected and verdict == Verdict.accepted:
        return "A rejected figure can only be corrected"
    return None


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
    table row, a number of its paragraph, or nothing for a typed value. Its id is the Review's,
    given now so the KPI values computed with the check name the same one."""

    verdict: Verdict
    reviewer: str
    reviewed_at: datetime
    correction: Correction | None = None
    cell_id: str | None = None
    quoted: QuotedSource | None = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))

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
