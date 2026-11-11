"""Daily closes (#26, #19 R11): backfill, the daily run, the CSV import and the replay of the
raw archive, and what the dossier shows. Each run first refreshes the exchange's listings.

A run writes each share in its own transaction: a backfill takes minutes, and a failure at one
share keeps every share written before it (an exception to "one use case, one transaction",
recorded in AGENTS.md). A source error at one share is that share's error; the run goes on.
"""

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from bloomberg_invest.adapters.prices import PriceArchive, PriceSource, PriceSourceError
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.prices import (
    DRIFT_DAYS,
    HISTORY_YEARS,
    MANUAL,
    Close,
    Holiday,
    ListedShare,
    StoredClose,
    change_from_previous,
    csv_closes,
    drift,
    expected_sessions,
    history_start,
    listing_key,
    missing_sessions,
    one_per_session,
    windows,
    years_before,
)
from bloomberg_invest.views import LastClose, Listing, PricePoint, PriceSeries

Clock = Callable[[], datetime]


@dataclass
class Report:
    """What a run did, a line per share worth naming; `errors` make the run fail."""

    added: int = 0
    lines: list[str] = field(default_factory=list)
    drift: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def refresh_listings(
    store: GraphStore, source: PriceSource, isins: dict[str, str], now: Clock, report: Report
) -> list[ListedShare]:
    """Store the shares the exchange lists today; name the ones it no longer lists."""
    shares = source.listings()
    for ticker in store.upsert_listings(source.mic, shares, isins, now()):
        report.lines.append(f"{ticker}: no longer listed; its closes are kept")
    return shares


def backfill(
    store: GraphStore,
    source: PriceSource,
    isins: dict[str, str],
    today: date,
    now: Clock,
    tickers: list[str] | None = None,
) -> Report:
    """Every session the source still has for each share, in windows of one year or less."""
    report = Report()
    shares = refresh_listings(store, source, isins, now, report)
    chosen = [s.ticker for s in shares if tickers is None or s.ticker in tickers]
    for unknown in sorted(set(tickers or []) - set(chosen)):
        report.errors.append(f"{unknown}: not listed by {source.source}")
    start_hint: date | None = None  # where the history starts, the same for every share
    for ticker in chosen:
        try:
            start_hint = _backfill_share(store, source, ticker, today, now, start_hint, report)
        except PriceSourceError as error:
            report.errors.append(f"{ticker}: {error}")
    return report


def _backfill_share(
    store: GraphStore,
    source: PriceSource,
    ticker: str,
    today: date,
    now: Clock,
    start_hint: date | None,
    report: Report,
) -> date | None:
    """One share's history, newest window first; returns where the history starts."""
    key, sessions, added = listing_key(ticker, source.mic), [], 0
    history = windows(years_before(today, HISTORY_YEARS) + timedelta(days=1), today)
    for n, (first, last) in enumerate(history):
        fetched = source.closes(ticker, first, last)
        if not fetched and n == 0:
            report.errors.append(f"{ticker}: no sessions from {first} to {last}")
            break
        if not fetched:
            found = _locate_history(source, ticker, first, last, start_hint)
            if found is None:
                break  # no history this far back
            start_hint, fetched = found
        sessions += fetched
        added += store.add_prices(key, fetched, source.source, source.currency, now())
        if start_hint and first <= start_hint:
            break
    report.added += added
    if sessions:
        span = f"{min(c.session for c in sessions)} to {max(c.session for c in sessions)}"
        report.lines.append(f"{ticker}: {len(sessions)} sessions, {span}, {added} new")
    return start_hint


def _locate_history(
    source: PriceSource, ticker: str, first: date, last: date, hint: date | None
) -> tuple[date, list[Close]] | None:
    """Where the source's history starts within `first`..`last`, with the sessions from there;
    None if it has none there."""
    answers: dict[date, list[Close]] = {}

    def has_rows(day: date) -> bool:
        if day not in answers:
            answers[day] = source.closes(ticker, day, last)
        return bool(answers[day])

    # The start found for the share before, if it is exactly where the history starts here too.
    if hint and first <= hint <= last and has_rows(hint) and not has_rows(hint - timedelta(days=1)):
        return hint, answers[hint]
    # Step a month at a time to the first start that answers, then halve back.
    after = first
    for at in (first + timedelta(days=30 * k) for k in range(1, 13)):
        if at > last:
            return None
        if has_rows(at):
            found = history_start(after, at, has_rows)
            has_rows(found)
            return found, answers[found]
        after = at
    return None


def daily(
    store: GraphStore, source: PriceSource, isins: dict[str, str], today: date, now: Clock
) -> Report:
    """Each listed share's sessions since its last stored one, checked against the exchange's
    calendar, and the last month read again for drift."""
    report = Report()
    shares = refresh_listings(store, source, isins, now, report)
    holidays = source.holidays()
    for share in shares:
        try:
            _daily_share(store, source, share.ticker, holidays, today, now, report)
        except PriceSourceError as error:
            report.errors.append(f"{share.ticker}: {error}")
    return report


def _daily_share(
    store: GraphStore,
    source: PriceSource,
    ticker: str,
    holidays: list[Holiday],
    today: date,
    now: Clock,
    report: Report,
) -> None:
    key = listing_key(ticker, source.mic)
    last = store.last_session(key, source.source)
    if last is None:
        report.lines.append(f"{ticker}: no closes yet; run bloomberg prices backfill")
        return
    start = min(last + timedelta(days=1), today - timedelta(days=DRIFT_DAYS))
    fetched: list[Close] = []
    for first, end in reversed(windows(start, today)):
        fetched += source.closes(ticker, first, end)
    kept = store.prices(key, since=start)
    # Today may not be published yet: it is checked on the next run.
    if not fetched and expected_sessions(start, today - timedelta(days=1), holidays):
        report.errors.append(f"{ticker}: empty answer from {start} to {today}")
    else:
        got = {c.session for c in fetched}
        missing = missing_sessions(
            last + timedelta(days=1), today - timedelta(days=1), got, holidays
        )
        report.errors += [f"{ticker}: no row for {d}" for d in missing]
    stored_days = {c.session for c in kept if c.source == source.source}
    late = [c.session for c in fetched if c.close is not None and c.session <= last]
    report.drift += [f"{ticker} {d}: appeared at the source" for d in late if d not in stored_days]
    report.drift += [
        f"{ticker} {line}" for line in drift(start, today, kept, fetched, source.source)
    ]
    no_close = [c.session for c in fetched if c.close is None and c.session > last]
    if no_close:
        report.lines.append(
            f"{ticker}: no close for {len(no_close)} sessions, latest {max(no_close)} (suspended?)"
        )
    report.added += store.add_prices(key, fetched, source.source, source.currency, now())


def import_csv(store: GraphStore, text: str, mic: str, currency: str, now: Clock) -> Report:
    """Closes typed in by hand fill the sessions no source gave; one already closed is kept.
    `currency` is the exchange's, for rows that name none."""
    report = Report()
    rows, refused = csv_closes(text, currency)
    report.errors += refused
    known = set(store.tickers(mic))
    groups: dict[tuple[str, str], list[Close]] = defaultdict(list)
    for row in rows:
        if row.ticker not in known:
            report.errors.append(f"{row.ticker} {row.session}: no such listing on {mic}")
            continue
        groups[(row.ticker, row.currency)].append(Close(row.session, row.close))
    at = now()
    for (ticker, written_currency), closes in sorted(groups.items()):
        key = listing_key(ticker, mic)
        have = {c.session for c in store.prices(key, since=min(c.session for c in closes))}
        fill = [c for c in closes if c.session not in have]
        added = store.add_prices(key, fill, MANUAL, written_currency, at)
        report.added += added
        skipped = len(closes) - len(fill)
        report.lines.append(
            f"{ticker}: {added} added" + (f", {skipped} skipped: already closed" if skipped else "")
        )
    return report


def replay(
    store: GraphStore,
    archive: PriceArchive,
    source: PriceSource,
    isins: dict[str, str],
    now: Clock,
) -> Report:
    """Rebuild the stored closes from the raw answers archived, by the same rules: each close
    keeps the time its answer was fetched, and a later answer supersedes an earlier one."""
    report = Report()
    shares = archive.listings()
    store.upsert_listings(source.mic, shares, isins, now())
    listed = {s.ticker for s in shares}
    added: dict[str, int] = defaultdict(int)
    unlisted: set[str] = set()
    for ticker, fetched_at, closes in archive.closes():
        if ticker not in listed:
            unlisted.add(ticker)
            continue
        added[ticker] += store.add_prices(
            listing_key(ticker, source.mic), closes, source.source, source.currency, fetched_at
        )
    report.errors += [f"{t}: closes archived, but in no listing archived" for t in sorted(unlisted)]
    report.added = sum(added.values())
    report.lines += [f"{t}: {n} new" for t, n in sorted(added.items()) if n]
    return report


def _listing_closes(
    store: GraphStore, isin: str, since: date | None = None
) -> tuple[Listing | None, list[StoredClose]]:
    """The company's listing, and its closes one per session from `since`, oldest first."""
    listing = store.listing(isin)
    if listing is None:
        return None, []
    key = listing_key(listing.ticker, listing.mic)
    return listing, one_per_session(store.prices(key, since=since))


def listing_and_last_close(store: GraphStore, isin: str) -> tuple[Listing | None, LastClose | None]:
    """The company's listing and its latest close, as the dossier shows them."""
    listing, closes = _listing_closes(store, isin)
    if not closes:
        return listing, None
    last, moved = closes[-1], change_from_previous(closes)
    return listing, LastClose(
        session=last.session,
        close=str(last.close),
        currency=last.currency,
        change=None if moved is None else str(moved),
        source=last.source,
        history_start=closes[0].session,
    )


def price_series(store: GraphStore, isin: str, today: date) -> PriceSeries | None:
    """The company's closes over the last three years, one per session."""
    listing, closes = _listing_closes(store, isin, since=years_before(today, HISTORY_YEARS))
    if listing is None:
        return None
    return PriceSeries(
        listing=listing, closes=[PricePoint(session=c.session, close=str(c.close)) for c in closes]
    )
