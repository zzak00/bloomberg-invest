"""Daily closes end to end on the test Neo4j (#26 AC1-AC3): backfill, the daily run, the CSV
import and the replay of the raw archive, with a source that behaves as the Bourse does."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from fakes import FakePriceSource

from bloomberg_invest.adapters.prices.bourse_casablanca import BourseCasablanca, RawArchive
from bloomberg_invest.domain.prices import MANUAL, Holiday, ListedShare, expected_sessions
from bloomberg_invest.service_layer.prices import (
    backfill,
    daily,
    import_csv,
    last_close,
    price_series,
    replay,
)

TODAY = date(2026, 11, 11)
HISTORY = date(2023, 11, 13)  # where the source's rolling three years start
HOLIDAYS = [
    Holiday(date(2026, 11, 6), confirmed=True),
    Holiday(date(2026, 11, 18), confirmed=True),
    Holiday(date(2026, 11, 4), confirmed=False),
]
ABC = ListedShare("ABC", "ALPHA BETA", "Télécommunications", "Principal A")
GAM = ListedShare("GAM", "GAMMA", "Banques", "Principal B")
ISINS = {"ABC": "MA0000011488"}
SOURCE = "bourse-casablanca"


def now() -> datetime:
    return datetime(2026, 11, 11, 18, 30, tzinfo=UTC)


def history(until: date = TODAY, base: str = "50", no_close: tuple[date, ...] = ()):
    """A close for every session from the history start, rising a cent a session."""
    days = expected_sessions(HISTORY, until, HOLIDAYS)
    return {
        d: None if d in no_close else Decimal(base) + Decimal(n) / 100 for n, d in enumerate(days)
    }


def exchange(**kwargs) -> FakePriceSource:
    sessions = kwargs.pop("sessions", {"ABC": history(), "GAM": history(base="600")})
    return FakePriceSource([ABC, GAM], sessions, HISTORY, HOLIDAYS, **kwargs)


def test_a_backfill_stores_every_session_the_source_still_has(store, document):
    source = exchange()
    report = backfill(store, source, ISINS, TODAY, now)
    assert report.errors == []
    sessions = len(history())
    assert report.added == 2 * sessions
    assert report.lines[0] == f"ABC: {sessions} sessions, 2023-11-13 to 2026-11-11, {sessions} new"
    # Every request asks for a year or less.
    assert all((end - start).days < 366 for _, start, end in source.asked)
    # The second share starts where the first one's history did: two requests to confirm it.
    gam = [a for a in source.asked if a[0] == "GAM"]
    abc = [a for a in source.asked if a[0] == "ABC"]
    assert len(gam) == 5 and len(abc) > len(gam)
    assert backfill(store, source, ISINS, TODAY, now).added == 0


def test_a_backfill_of_one_share_and_one_the_exchange_does_not_list(store):
    report = backfill(store, exchange(), {}, TODAY, now, tickers=["GAM", "XYZ"])
    assert report.errors == ["XYZ: not listed by bourse-casablanca"]
    assert [line.split(":")[0] for line in report.lines] == ["GAM"]


def test_a_backfill_with_nothing_this_year_is_an_error(store):
    report = backfill(store, exchange(sessions={}), {}, TODAY, now)
    assert report.errors == [
        "ABC: no sessions from 2025-11-12 to 2026-11-11",
        "GAM: no sessions from 2025-11-12 to 2026-11-11",
    ]


def backfilled(store, until: date) -> None:
    backfill(
        store,
        exchange(sessions={"ABC": history(until), "GAM": history(until, "600")}),
        ISINS,
        until,
        now,
    )


def test_the_daily_run_adds_the_sessions_since_the_last_one(store, document):
    backfilled(store, date(2026, 11, 3))
    report = daily(store, exchange(), ISINS, TODAY, now)
    assert (report.errors, report.drift) == ([], [])
    # 5 (the 4th may be a holiday, but the exchange traded), 9, 10 and 11: the 6th is closed.
    assert report.added == 2 * 5
    assert daily(store, exchange(), ISINS, TODAY, now).added == 0


def test_a_missing_session_is_an_error_but_an_unconfirmed_holiday_is_not(store):
    backfilled(store, date(2026, 11, 3))
    sessions = history()
    for day in (date(2026, 11, 4), date(2026, 11, 9)):
        del sessions[day]
    report = daily(
        store, exchange(sessions={"ABC": sessions, "GAM": history(base="600")}), {}, TODAY, now
    )
    assert report.errors == ["ABC: no row for 2026-11-09"]


def test_an_empty_answer_is_an_error(store):
    backfilled(store, date(2026, 11, 3))
    report = daily(store, exchange(sessions={"GAM": history(base="600")}), {}, TODAY, now)
    assert report.errors == ["ABC: empty answer from 2026-10-12 to 2026-11-11"]


def test_today_is_taken_if_published_and_checked_next_run(store):
    backfilled(store, date(2026, 11, 10))
    report = daily(
        store,
        exchange(sessions={"ABC": history(date(2026, 11, 10)), "GAM": history(base="600")}),
        {},
        TODAY,
        now,
    )
    assert report.errors == []
    assert report.added == 1  # GAM's 11th


def test_drift_is_reported_and_never_overwrites(store):
    backfilled(store, date(2026, 11, 3))
    sessions = history()
    sessions[date(2026, 11, 2)] += Decimal("0.05")  # the source changed a stored close
    del sessions[date(2026, 10, 30)]  # and dropped one
    report = daily(
        store, exchange(sessions={"ABC": sessions, "GAM": history(base="600")}), {}, TODAY, now
    )
    stored = {c.session: c.close for c in store.prices("XCAS:ABC", since=date(2026, 10, 30))}
    assert report.drift == [
        f"ABC 2026-10-30: stored {stored[date(2026, 10, 30)]}, source has no close now",
        f"ABC 2026-11-02: stored {stored[date(2026, 11, 2)]}, source now {sessions[date(2026, 11, 2)]}",
    ]
    assert stored[date(2026, 11, 2)] == history()[date(2026, 11, 2)]


def test_a_share_with_no_close_is_noted_not_failed(store):
    backfilled(store, date(2026, 11, 3))
    suspended = history(no_close=tuple(expected_sessions(date(2026, 11, 4), TODAY, HOLIDAYS)))
    report = daily(
        store, exchange(sessions={"ABC": suspended, "GAM": history(base="600")}), {}, TODAY, now
    )
    assert report.errors == []
    assert "ABC: no close for 5 sessions, latest 2026-11-11 (suspended?)" in report.lines


def test_a_share_never_backfilled_is_named(store):
    backfill(store, exchange(), {}, TODAY, now, tickers=["GAM"])
    report = daily(store, exchange(), {}, TODAY, now)
    assert "ABC: no closes yet; run bloomberg prices backfill" in report.lines


def test_a_csv_fills_gaps_by_hand_and_keeps_what_is_stored(store):
    backfilled(store, date(2026, 11, 3))
    text = 'ticker,date,close\nABC,2026-11-03,1\nABC,2026-11-05,"88,90"\nXYZ,2026-11-05,2\nABC,soon,3\n'
    report = import_csv(store, text, now)
    assert report.added == 1
    assert report.lines == ["ABC: 1 added, 1 skipped: already closed"]
    assert report.errors == [
        "line 5: 'soon' is not a date (YYYY-MM-DD)",
        "XYZ 2026-11-05: no such listing on XCAS",
    ]
    [manual] = [c for c in store.prices("XCAS:ABC") if c.source == MANUAL]
    assert (manual.session, manual.close) == (date(2026, 11, 5), Decimal("88.90"))


def test_the_dossier_shows_the_last_close_its_change_and_three_years(store, document):
    backfilled(store, date(2026, 11, 10))
    listing, last = last_close(store, "MA0000011488")
    assert (listing.ticker, listing.sector) == ("ABC", "Télécommunications")
    closes = history(date(2026, 11, 10))
    final, before = closes[date(2026, 11, 10)], closes[date(2026, 11, 9)]
    assert (last.session, Decimal(last.close), last.source) == (date(2026, 11, 10), final, SOURCE)
    assert Decimal(last.change) == ((final - before) / before).quantize(Decimal("0.0001"))
    assert last.history_start == HISTORY
    series = price_series(store, "MA0000011488", TODAY)
    assert (series.closes[0].session, series.closes[-1].session) == (HISTORY, date(2026, 11, 10))
    assert last_close(store, "MA0000000000") == (None, None)


FIXTURES = Path(__file__).parents[1] / "fixtures" / "bourse"


def test_the_archive_rebuilds_the_same_closes(store, tmp_path, driver):
    def fetch(url: str) -> bytes:
        if url.endswith("/emetteurs/liste-emetteurs"):
            return (FIXTURES / "issuers.html").read_bytes()
        return (FIXTURES / "closes.json").read_bytes()

    archive = RawArchive(tmp_path)
    source = BourseCasablanca(fetch=fetch, archive=archive, pause=0, clock=now)
    backfill(store, source, {}, TODAY, now, tickers=["ABC"])
    before = store.prices("XCAS:ABC")
    assert before
    driver.execute_query("MATCH (p:Price) DETACH DELETE p")
    report = replay(store, archive, source, {}, now)
    assert report.lines == [f"ABC: {len(before)} new"]
    assert store.prices("XCAS:ABC") == before
    assert replay(store, archive, source, {}, now).added == 0


def test_dates_are_one_day_apart_in_the_history_helper():
    days = list(history(date(2023, 11, 20)))
    assert days[0] == HISTORY and days[1] - days[0] == timedelta(days=1)
