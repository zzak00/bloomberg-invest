"""`bloomberg prices ...`: daily closes from the Bourse de Casablanca (#26).

    bloomberg prices backfill [--ticker IAM]   three years of closes per listed share
    bloomberg prices daily                     every session since the last one, checked
    bloomberg prices import closes.csv         closes typed in by hand (ticker,date,close)
    bloomberg prices replay                    rebuild the closes from the raw answers kept
    bloomberg prices schedule --at 18:30       `daily` now, then every day at that time

Each prints a line per share worth naming, then drift and errors; it exits 1 on any error.
"""

import argparse
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from neo4j.exceptions import DriverError, Neo4jError

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.prices import PriceSourceError
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.prices import CASABLANCA, XCAS
from bloomberg_invest.service_layer.prices import Report, backfill, daily, import_csv, replay
from bloomberg_invest.settings import Settings

# What stops a run before it reports: the source, the input, the disk or the database.
FAILURES = (PriceSourceError, ValueError, OSError, Neo4jError, DriverError)


def add_arguments(commands: argparse._SubParsersAction) -> None:
    prices = commands.add_parser("prices", help="daily closes from the Bourse de Casablanca")
    prices.add_argument("--mic", default=XCAS, help="the exchange (ISO 10383), default XCAS")
    steps = prices.add_subparsers(dest="step", required=True)
    backfill_cmd = steps.add_parser("backfill", help="three years of closes per listed share")
    backfill_cmd.add_argument("--ticker", action="append", help="only this share (repeatable)")
    steps.add_parser("daily", help="every session since the last one, checked for drift")
    import_cmd = steps.add_parser("import", help="closes typed in by hand, from a CSV")
    import_cmd.add_argument("csv", type=Path)
    steps.add_parser("replay", help="rebuild the stored closes from the raw answers kept")
    schedule_cmd = steps.add_parser("schedule", help="run `daily` now, then every day")
    schedule_cmd.add_argument(
        "--at", type=clock_time, default="18:30", help="Casablanca time, HH:MM"
    )


def run(args: argparse.Namespace) -> int:
    if args.step == "schedule":
        return _schedule(args)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    try:
        with bootstrap.connect(settings) as deps:
            report = _call(args, deps.store, bootstrap.prices(settings, args.mic))
    except FAILURES as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return _print(report)


def _call(args: argparse.Namespace, store: GraphStore, prices: bootstrap.Prices) -> Report:
    """The one service function the step names."""
    source, isins = prices.source, prices.isins
    if args.step == "backfill":
        return backfill(store, source, isins, _today(), _now, tickers=args.ticker)
    if args.step == "daily":
        return daily(store, source, isins, _today(), _now)
    if args.step == "import":
        text = args.csv.read_text(encoding="utf-8")
        return import_csv(store, text, source.mic, source.currency, _now)
    return replay(store, prices.archive, source, isins, _now)


def _print(report: Report) -> int:
    for line in report.lines:
        print(line)
    for line in report.drift:
        print(f"drift: {line}")
    for line in report.errors:
        print(f"error: {line}", file=sys.stderr)
    print(
        f"{_count(report.added, 'new close')}, {len(report.drift)} drifted, "
        f"{_count(len(report.errors), 'error')}",
        file=sys.stderr if report.errors else sys.stdout,
    )
    return 1 if report.errors else 0


def _count(n: int, thing: str) -> str:
    return f"{n} {thing}" if n == 1 else f"{n} {thing}s"


def _schedule(args: argparse.Namespace) -> int:
    """`daily` now, then every day at `--at` Casablanca time, for as long as the process runs. A
    failed run is printed and the next one goes ahead: it catches up from the last session."""
    hour, minute = args.at
    daily_args = argparse.Namespace(step="daily", mic=args.mic)
    while True:
        print(f"{datetime.now(CASABLANCA):%Y-%m-%d %H:%M} daily closes", flush=True)
        _run(daily_args)
        sys.stdout.flush()
        time.sleep(_until(datetime.now(CASABLANCA), hour, minute).total_seconds())


def clock_time(text: str) -> tuple[int, int]:
    """`18:30` as (18, 30); anything else is refused with argparse's usage message."""
    try:
        hour, minute = (int(part) for part in text.split(":"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a time like 18:30") from None
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise argparse.ArgumentTypeError(f"{text!r} is not a time like 18:30")
    return hour, minute


def _until(now: datetime, hour: int, minute: int) -> timedelta:
    """How long from `now` to the next `hour:minute` the same day or the next."""
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target - now


def _today() -> date:
    return datetime.now(CASABLANCA).date()


def _now() -> datetime:
    return datetime.now(UTC)
