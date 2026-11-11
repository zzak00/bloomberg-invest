"""The daily closes schedule (#26 D3): `daily` runs every day at a set Casablanca time."""

import argparse
from datetime import datetime, timedelta

import pytest

from bloomberg_invest.domain.prices import CASABLANCA
from bloomberg_invest.entrypoints.prices import _until, clock_time


def test_the_next_run_is_today_if_its_time_has_not_come():
    now = datetime(2026, 11, 11, 9, 0, tzinfo=CASABLANCA)
    assert _until(now, 18, 30) == timedelta(hours=9, minutes=30)


def test_the_next_run_is_tomorrow_once_its_time_has_passed():
    now = datetime(2026, 11, 11, 18, 30, tzinfo=CASABLANCA)
    assert _until(now, 18, 30) == timedelta(days=1)


def test_a_run_time_is_hours_and_minutes():
    assert clock_time("18:30") == (18, 30)
    for bad in ("18h30", "25:00", "18:60", ""):
        with pytest.raises(argparse.ArgumentTypeError, match="is not a time like 18:30"):
            clock_time(bad)
