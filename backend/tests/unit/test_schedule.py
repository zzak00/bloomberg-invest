"""The daily closes schedule (#26 D3): `daily` runs every day at a set Casablanca time."""

from datetime import datetime, timedelta

from bloomberg_invest.entrypoints.prices import CASABLANCA, _until


def test_the_next_run_is_today_if_its_time_has_not_come():
    now = datetime(2026, 11, 11, 9, 0, tzinfo=CASABLANCA)
    assert _until(now, 18, 30) == timedelta(hours=9, minutes=30)


def test_the_next_run_is_tomorrow_once_its_time_has_passed():
    now = datetime(2026, 11, 11, 18, 30, tzinfo=CASABLANCA)
    assert _until(now, 18, 30) == timedelta(days=1)
