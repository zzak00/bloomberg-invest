"""Daily closes (#19 R11, #26): how a share's closes are fetched, checked and shown.

A Price is a daily close of one Listing: market data, not a Fact. A close that changes at the
source is reported as drift, and the new one supersedes the stored one, which is kept (#19 R4).
"""

import csv
import io
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from bloomberg_invest.domain.figures import parse_value

# The Bourse de Casablanca's market identifier code (ISO 10383), and its clock: a session is a
# day in Casablanca.
XCAS = "XCAS"
CASABLANCA = ZoneInfo("Africa/Casablanca")
# The source of a close typed in by hand, from a CSV (#26 AC3).
MANUAL = "manual"
# How much history a backfill asks for: the Bourse keeps a rolling three years (#15).
HISTORY_YEARS = 3
# How far back the daily run reads again to look for drift.
DRIFT_DAYS = 30


@dataclass(frozen=True)
class ListedShare:
    """A share as the exchange lists it."""

    ticker: str
    name: str
    sector: str
    compartment: str


@dataclass(frozen=True)
class Holiday:
    """A day the exchange is closed. A moon-dated holiday is unconfirmed until it is announced."""

    day: date
    confirmed: bool


@dataclass(frozen=True)
class Close:
    """One session as the source gives it; `close` is None when the share has none that day,
    as for a suspended share."""

    session: date
    close: Decimal | None


@dataclass(frozen=True)
class StoredClose:
    """A close as stored, with where it came from."""

    session: date
    close: Decimal
    source: str
    currency: str


@dataclass(frozen=True)
class CsvClose:
    """A close typed in by hand."""

    ticker: str
    session: date
    close: Decimal
    currency: str


def listing_key(ticker: str, mic: str) -> str:
    """What a Price names its Listing by: `XCAS:IAM`."""
    return f"{mic}:{ticker}"


def years_before(day: date, years: int) -> date:
    """The same day `years` earlier; the 29th of February becomes the 28th."""
    try:
        return day.replace(year=day.year - years)
    except ValueError:
        return day.replace(year=day.year - years, day=28)


def windows(start: date, end: date) -> list[tuple[date, date]]:
    """`start` to `end` cut into windows of one year or less, newest first: the source answers
    a longer range with nothing (#15)."""
    out = []
    while end >= start:
        first = max(start, years_before(end, 1) + timedelta(days=1))
        out.append((first, end))
        end = first - timedelta(days=1)
    return out


def expected_sessions(start: date, end: date, holidays: list[Holiday]) -> list[date]:
    """The days from `start` to `end` the exchange should trade: weekdays that are not a
    confirmed holiday."""
    closed = {h.day for h in holidays if h.confirmed}
    days = (start + timedelta(days=n) for n in range((end - start).days + 1))
    return [d for d in days if d.weekday() < 5 and d not in closed]


def missing_sessions(
    start: date, end: date, given: set[date], holidays: list[Holiday]
) -> list[date]:
    """Expected sessions the source gave no row for. Every listed share has a row each session,
    traded or not (checked 2026-11-10), so a missing row is a failure; a day that may be an
    unconfirmed holiday is not."""
    maybe_closed = {h.day for h in holidays if not h.confirmed}
    return [
        d
        for d in expected_sessions(start, end, holidays)
        if d not in given and d not in maybe_closed
    ]


def drift(
    start: date, end: date, kept: list[StoredClose], fetched: list[Close], source: str
) -> list[str]:
    """How the source's closes from `start` to `end` differ from the ones stored from it: a
    close that changed, or one it no longer gives. New sessions are not drift: they are added."""
    now = {c.session: c.close for c in fetched if c.close is not None}
    lines = []
    for c in sorted(kept, key=lambda c: c.session):
        if c.source != source or not start <= c.session <= end:
            continue
        if c.session not in now:
            lines.append(f"{c.session}: stored {c.close}, source has no close now")
        elif now[c.session] != c.close:
            lines.append(f"{c.session}: stored {c.close}, source now {now[c.session]}")
    return lines


def csv_closes(text: str, currency: str) -> tuple[list[CsvClose], list[str]]:
    """The closes of a CSV with the columns `ticker,date,close` and an optional `currency`
    (the exchange's `currency` by default), and a line for each row refused. Dates are ISO (`2026-11-05`); a close
    may be written either way (`88,90` or `88.90`)."""
    reader = csv.DictReader(io.StringIO(text))
    if not {"ticker", "date", "close"} <= set(reader.fieldnames or []):
        raise ValueError("a closes CSV needs the columns ticker,date,close (and maybe currency)")
    rows, refused = [], []
    for line, row in enumerate(reader, start=2):
        written = (row["close"] or "").strip()
        try:
            session = date.fromisoformat((row["date"] or "").strip())
        except ValueError:
            refused.append(f"line {line}: {row['date']!r} is not a date (YYYY-MM-DD)")
            continue
        value = parse_value(written)
        if value is None:
            refused.append(f"line {line}: {written!r} is not one number")
            continue
        written_currency = (row.get("currency") or currency).strip().upper()
        rows.append(
            CsvClose((row["ticker"] or "").strip().upper(), session, value, written_currency)
        )
    return rows, refused


def one_per_session(closes: list[StoredClose]) -> list[StoredClose]:
    """One close per session, oldest first: the exchange's over one typed in by hand."""
    best: dict[date, StoredClose] = {}
    for c in closes:
        if c.session not in best or best[c.session].source == MANUAL:
            best[c.session] = c
    return [best[d] for d in sorted(best)]


def change_from_previous(closes: list[StoredClose]) -> Decimal | None:
    """The last close's change from the session before, as a fraction to four places."""
    if len(closes) < 2:
        return None
    before, last = closes[-2].close, closes[-1].close
    return ((last - before) / before).quantize(Decimal("0.0001"))


def history_start(after: date, at: date, has_rows: Callable[[date], bool]) -> date:
    """The earliest start from which the source answers, between `after` (where it answers
    nothing) and `at` (where it does): it answers nothing for a range starting before its
    history (#15). Halves the gap until it is one day."""
    while (at - after).days > 1:
        middle = after + timedelta(days=(at - after).days // 2)
        if has_rows(middle):
            at = middle
        else:
            after = middle
    return at
