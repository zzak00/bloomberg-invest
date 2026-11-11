"""Daily closes (#26, #19 R11): the rules for fetching, checking and storing them."""

from datetime import date
from decimal import Decimal

import pytest

from bloomberg_invest.domain.prices import (
    MANUAL,
    Close,
    Holiday,
    StoredClose,
    change_from_previous,
    csv_closes,
    drift,
    expected_sessions,
    history_start,
    missing_sessions,
    one_per_session,
    windows,
)

HOLIDAYS = [
    Holiday(date(2026, 11, 6), confirmed=True),  # Green March
    Holiday(date(2026, 11, 18), confirmed=True),  # Independence Day
    Holiday(date(2026, 5, 27), confirmed=False),  # moon-dated
]


def test_a_range_is_fetched_in_windows_of_one_year_or_less_newest_first():
    assert windows(date(2023, 11, 12), date(2026, 11, 11)) == [
        (date(2025, 11, 12), date(2026, 11, 11)),
        (date(2024, 11, 12), date(2025, 11, 11)),
        (date(2023, 11, 12), date(2024, 11, 11)),
    ]
    assert windows(date(2026, 11, 9), date(2026, 11, 11)) == [
        (date(2026, 11, 9), date(2026, 11, 11))
    ]
    assert windows(date(2026, 11, 12), date(2026, 11, 11)) == []


def test_sessions_are_weekdays_that_are_not_a_confirmed_holiday():
    assert expected_sessions(date(2026, 11, 2), date(2026, 11, 9), HOLIDAYS) == [
        date(2026, 11, 2),
        date(2026, 11, 3),
        date(2026, 11, 4),
        date(2026, 11, 5),
        date(2026, 11, 9),
    ]


def test_a_session_with_no_row_is_missing_unless_it_may_be_a_holiday():
    got = {date(2026, 11, 2), date(2026, 11, 4)}
    assert missing_sessions(date(2026, 11, 2), date(2026, 11, 5), got, HOLIDAYS) == [
        date(2026, 11, 3),
        date(2026, 11, 5),
    ]
    # The 27th of May may be Eid: no row then is not an error.
    assert missing_sessions(date(2026, 5, 27), date(2026, 5, 27), set(), HOLIDAYS) == []


def close(day: int, value: str | None, month: int = 11) -> Close:
    return Close(session=date(2026, month, day), close=None if value is None else Decimal(value))


def stored(day: int, value: str, source: str = "bourse-casablanca") -> StoredClose:
    return StoredClose(date(2026, 11, day), Decimal(value), source, "MAD")


def test_drift_names_each_session_that_changed_vanished_or_appeared():
    fetched = [close(3, "88.90"), close(4, "88.95"), close(9, "89.80")]
    kept = [stored(3, "88.90"), stored(4, "88.90"), stored(5, "88.70")]
    assert drift(date(2026, 11, 3), date(2026, 11, 5), kept, fetched, "bourse-casablanca") == [
        "2026-11-04: stored 88.90, source now 88.95",
        "2026-11-05: stored 88.70, source has no close now",
    ]


def test_drift_ignores_manual_closes_and_sessions_outside_the_range():
    kept = [stored(5, "88.70", source=MANUAL), stored(12, "90")]
    assert drift(date(2026, 11, 3), date(2026, 11, 9), kept, [], "bourse-casablanca") == []


def test_a_csv_gives_closes_and_says_which_lines_it_refused():
    text = 'ticker,date,close\nIAM,2026-11-05,"88,90"\nIAM,2026-11-09,89.80\nIAM,09/11/2026,1\nATW,2026-11-09,abc\n'
    rows, refused = csv_closes(text, "MAD")
    assert [(r.ticker, r.session, r.close, r.currency) for r in rows] == [
        ("IAM", date(2026, 11, 5), Decimal("88.90"), "MAD"),
        ("IAM", date(2026, 11, 9), Decimal("89.80"), "MAD"),
    ]
    assert refused == [
        "line 4: '09/11/2026' is not a date (YYYY-MM-DD)",
        "line 5: 'abc' is not one number",
    ]


def test_a_csv_without_the_columns_is_refused_whole():
    with pytest.raises(ValueError, match="ticker,date,close"):
        csv_closes("symbol,day,price\nIAM,2026-11-05,88.90\n", "MAD")


def test_the_bourse_close_is_shown_over_a_manual_one_on_the_same_session():
    closes = [
        stored(5, "88.80", source=MANUAL),
        stored(5, "88.90"),
        stored(4, "88.10", source=MANUAL),
    ]
    assert [(c.session.day, c.close, c.source) for c in one_per_session(closes)] == [
        (4, Decimal("88.10"), MANUAL),
        (5, Decimal("88.90"), "bourse-casablanca"),
    ]


def test_the_change_is_from_the_session_before():
    assert change_from_previous([stored(9, "89.80"), stored(10, "91.70")]) == Decimal("0.0212")
    assert change_from_previous([stored(10, "91.70")]) is None


def test_the_history_start_is_found_by_halving():
    start = date(2023, 11, 13)
    asked: list[date] = []

    def has_rows(day: date) -> bool:
        asked.append(day)
        return day >= start

    assert history_start(date(2023, 10, 12), date(2023, 12, 12), has_rows) == start
    assert len(asked) <= 6
