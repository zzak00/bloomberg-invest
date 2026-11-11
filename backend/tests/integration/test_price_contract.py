"""The PriceSource and PriceArchive contracts (#26): every implementation, and the fake the
service tests use, answers the same made-up exchange the same way.

The Bourse adapter reads the fixtures through `bourse_server`, a fetch that behaves as the
Bourse's server does.
"""

from collections.abc import Callable
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fakes import BOURSE_HISTORY, FakePriceSource, bourse_server

from bloomberg_invest.adapters.prices import PriceArchive, PriceSource
from bloomberg_invest.adapters.prices.bourse_casablanca import BourseCasablanca, RawArchive
from bloomberg_invest.domain.prices import Close, Holiday, ListedShare

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bourse"
HISTORY = BOURSE_HISTORY
SHARES = [
    ListedShare("ABC", "ALPHA BETA", "Télécommunications", "Principal A"),
    ListedShare("GAM", "GAMMA", "Banques", "Principal B"),
]
HOLIDAYS = [Holiday(date(2026, 11, 6), confirmed=True), Holiday(date(2026, 5, 27), confirmed=False)]
ABC = {
    date(2026, 11, 3): Decimal(50),
    date(2026, 11, 4): None,
    date(2026, 11, 5): Decimal("51.95"),
    date(2026, 11, 9): Decimal("52.4"),
}
AT = datetime(2026, 11, 10, 18, 30, tzinfo=UTC)


SOURCES: dict[str, Callable[[], PriceSource]] = {
    "bourse": lambda: BourseCasablanca(fetch=bourse_server, pause=0),
    "fake": lambda: FakePriceSource(SHARES, {"ABC": ABC}, HISTORY, HOLIDAYS),
}


@pytest.fixture(params=SOURCES, ids=list(SOURCES))
def source(request) -> PriceSource:
    return SOURCES[request.param]()


def test_a_source_names_its_exchange_source_and_currency(source):
    assert (source.mic, source.source, source.currency) == ("XCAS", "bourse-casablanca", "MAD")


def test_a_source_lists_the_exchange_s_shares(source):
    assert source.listings() == SHARES


def test_a_source_gives_the_exchange_s_holidays(source):
    assert source.holidays() == HOLIDAYS


def test_closes_come_oldest_first_and_a_session_may_have_none(source):
    assert source.closes("ABC", date(2026, 11, 2), date(2026, 11, 9)) == [
        Close(d, ABC[d]) for d in sorted(ABC)
    ]


def test_closes_are_only_those_of_the_range(source):
    closes = source.closes("ABC", date(2026, 11, 4), date(2026, 11, 5))
    assert [c.session for c in closes] == [date(2026, 11, 4), date(2026, 11, 5)]


def test_a_range_starting_before_the_history_or_an_unknown_share_gives_nothing(source):
    assert source.closes("ABC", date(2023, 11, 12), date(2024, 11, 11)) == []
    assert source.closes("XYZ", date(2026, 11, 2), date(2026, 11, 9)) == []


def raw_archive(root: Path) -> PriceArchive:
    """An archive the Bourse adapter filled: two listing pages, a week apart, then closes."""
    archive = RawArchive(root)
    issuers = (FIXTURES / "issuers.html").read_bytes()
    earlier, later = datetime(2026, 11, 2, tzinfo=UTC), datetime(2026, 11, 9, tzinfo=UTC)
    archive.save("listings/{at}.html", earlier, issuers.replace(b"GAMMA", b"GAMMA OLD"))
    archive.save("listings/{at}.html", later, issuers)
    BourseCasablanca(fetch=bourse_server, archive=archive, pause=0, clock=lambda: AT).closes(
        "ABC", date(2026, 11, 2), date(2026, 11, 9)
    )
    return archive


ARCHIVES: dict[str, Callable[[Path], PriceArchive]] = {"raw": raw_archive}


@pytest.fixture(params=ARCHIVES, ids=list(ARCHIVES))
def archive(request, tmp_path) -> PriceArchive:
    return ARCHIVES[request.param](tmp_path)


def test_an_archive_lists_every_share_as_its_latest_page_gave_it(archive):
    assert archive.listings() == SHARES


def test_an_archive_gives_back_each_answer_with_when_it_was_fetched(archive):
    assert [(t, at, c) for t, at, c in archive.closes()] == [
        ("ABC", AT, [Close(d, ABC[d]) for d in sorted(ABC)])
    ]
