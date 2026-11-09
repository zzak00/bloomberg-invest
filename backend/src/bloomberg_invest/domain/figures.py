"""Financial figures: values and units parsed in Python, and the check against the source (#19 R6).

The LLM copies a value as written and names its unit; it never computes. Python parses both, and
keeps a figure only when its value equals its cell's number or appears in its paragraph (#10).
"""

import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum

from bloomberg_invest.domain.label_map import Kind

SPACES = re.compile(r"[\s  ]+")
MINUS = ("-", "−", "–")
# The kind of Fact a financial figure is (#19 R5); other kinds of Fact come with later slices.
FINANCIAL_FIGURE = "financial_figure"


class Scope(StrEnum):
    consolidated = "consolidated"
    company_only = "company-only"


# Listed Moroccan groups report their consolidated accounts under IFRS and the parent's own
# accounts under the Moroccan code (CGNC), so the scope gives the standard.
STANDARD = {Scope.consolidated: "IFRS", Scope.company_only: "CGNC"}


def number(text: str) -> str:
    """A cell's digits, decimal comma and sign, ignoring spaces of every width (#10's check).

    `(988)` and `-988` are the same number; `36 681` and `36681` too.
    """
    text = text.strip()
    digits = re.sub(r"[^\d,]", "", text)
    return ("-" if _negative(text) and digits else "") + digits


def _negative(text: str) -> bool:
    """`-988`, `−988` and `(988)` are negative."""
    return text.startswith(MINUS) or (text.startswith("(") and text.endswith(")"))


def matches_cell(value: str, cell: str) -> bool:
    """A cell figure counts when its value is the cell's number: `1.5` is not `15`."""
    number = parse_value(value)
    return number is not None and number == parse_value(cell)


def matches_span(value: str, paragraph: str) -> bool:
    """A paragraph figure counts when its value, as written, appears in the paragraph."""
    quoted = SPACES.sub(" ", value).strip()
    return bool(quoted) and quoted in SPACES.sub(" ", paragraph)


def parse_value(text: str) -> Decimal | None:
    """The number a value is written as, or None when it is not one number.

    French notation: spaces group thousands and a comma marks decimals (`1 284,6`). A dot is
    read as a thousands separator when three digits follow it (`36.681`), otherwise as decimals.
    A sign, parentheses and a trailing `%` are allowed.
    """
    text = SPACES.sub("", text.strip())
    negative = _negative(text)
    text = text.strip("()").lstrip("".join(MINUS) + "+").removesuffix("%")
    if "," in text and "." in text:
        decimal = "," if text.rindex(",") > text.rindex(".") else "."
        text = text.replace("." if decimal == "," else ",", "").replace(",", ".")
    elif "," in text:
        text = text.replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", text):
        text = text.replace(".", "")
    if not re.fullmatch(r"\d+(\.\d+)?", text):
        return None
    value = Decimal(text)
    return -value if negative else value


@dataclass(frozen=True)
class Unit:
    """What a value counts: `MAD` (with its scale), `%`, `shares` or `MAD/share`."""

    unit: str
    scale: int = 1
    currency: str | None = None


CURRENCIES = {"mad": "MAD", "dh": "MAD", "dhs": "MAD", "dirhams": "MAD", "eur": "EUR", "usd": "USD"}
SCALES = {
    "thousands": 1_000,
    "thousand": 1_000,
    "milliers": 1_000,
    "k": 1_000,
    "millions": 1_000_000,
    "million": 1_000_000,
    "m": 1_000_000,
    "billions": 1_000_000_000,
    "billion": 1_000_000_000,
    "milliards": 1_000_000_000,
    "milliard": 1_000_000_000,
    "bn": 1_000_000_000,
    "mds": 1_000_000_000,
}
# Short forms filings use: MDH is millions of dirhams, KDH thousands.
COMPOUNDS = {
    "mdh": ("MAD", 1_000_000),
    "mmad": ("MAD", 1_000_000),
    "kdh": ("MAD", 1_000),
    "kmad": ("MAD", 1_000),
}
PER_SHARE = re.compile(r"\b(per|par)\s+(share|action)\b|/\s*(share|action)\b")
SHARES = {"shares", "actions", "titres"}


def parse_unit(text: str) -> Unit | None:
    """The unit the LLM named (`MAD millions`, `en milliers de dirhams`, `%`), or None."""
    text = text.strip().lower()
    if text in {"%", "percent", "pourcentage"}:
        return Unit("%")
    words = re.findall(r"[a-z%]+", text.replace("'", " "))
    if set(words) & SHARES and not PER_SHARE.search(text):
        return Unit("shares")
    currency, scale = None, 1
    for word in words:
        if word in COMPOUNDS:
            currency, scale = COMPOUNDS[word]
        elif word in CURRENCIES:
            currency = CURRENCIES[word]
        elif word in SCALES:
            scale = SCALES[word]
    if currency is None:
        return None
    if PER_SHARE.search(text):
        return Unit(f"{currency}/share", scale, currency) if scale == 1 else None
    return Unit(currency, scale, currency)


def scaled(value: Decimal, unit: Unit) -> str:
    """The value in its base unit, as an exact decimal string: `36 681` MAD millions is
    `36681000000`. Strings, because Neo4j has no decimal type and floats break equality."""
    exact = value * unit.scale
    text = format(exact.normalize(), "f")
    return "0" if text in {"-0", "0"} else text


@dataclass(frozen=True)
class Period:
    """A flow figure covers a fiscal year; a stock figure holds on its last day (AGENTS.md)."""

    start: date | None
    end: date | None
    as_of: date | None


def period(fiscal_year: int, kind: Kind) -> Period:
    """Fiscal years end on 31 December, as for every filing ingested so far; a filing with
    another year end needs its own rule here."""
    if kind == "stock":
        return Period(None, None, date(fiscal_year, 12, 31))
    return Period(date(fiscal_year, 1, 1), date(fiscal_year, 12, 31), None)
