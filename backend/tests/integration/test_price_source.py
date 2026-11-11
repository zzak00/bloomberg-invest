"""The PriceSource contract (#26 AC5): each source, on answers recorded in its own shape.

The Bourse fixtures are made-up closes in the Bourse's exact format (#26 D4): its data may not
be republished, and this repo is public. `test_bourse_replays_its_real_answers` reads the real
answers a backfill keeps in the gitignored `data/prices/raw/`, and skips without them.
"""

import json
import ssl
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from bloomberg_invest.adapters.prices import PriceSourceError
from bloomberg_invest.adapters.prices.bourse_casablanca import (
    BourseCasablanca,
    RawArchive,
    tls_context,
)
from bloomberg_invest.domain.prices import Close, Holiday, ListedShare

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bourse"
RECORDED = Path(__file__).parents[3] / "data" / "prices" / "raw"
AT = datetime(2026, 11, 10, 18, 30, tzinfo=UTC)


def serve(**closes: str):
    """A fetch that answers the pages from the fixtures, and closes by ticker (and page)."""
    asked: list[str] = []

    def fetch(url: str) -> bytes:
        asked.append(url)
        if url.endswith("/emetteurs/liste-emetteurs"):
            return (FIXTURES / "issuers.html").read_bytes()
        if url.endswith("/market-data/jours-feries"):
            return (FIXTURES / "holidays.html").read_bytes()
        query = parse_qs(urlparse(url).query)
        name = closes.get(f"{query['instrument'][0]}_p{query['pageNumber'][0]}") or closes.get(
            query["instrument"][0], "empty.json"
        )
        return (FIXTURES / name).read_bytes()

    fetch.asked = asked
    return fetch


def bourse(fetch, **kwargs) -> BourseCasablanca:
    return BourseCasablanca(fetch=fetch, pause=0, clock=lambda: AT, **kwargs)


def test_shares_come_from_the_issuer_list_with_their_sector():
    assert bourse(serve()).listings() == [
        ListedShare("ABC", "ALPHA BETA", "Télécommunications", "Principal A"),
        ListedShare("GAM", "GAMMA", "Banques", "Principal B"),
    ]


def test_holidays_say_whether_they_are_confirmed():
    assert bourse(serve()).holidays() == [
        Holiday(date(2026, 11, 6), confirmed=True),
        Holiday(date(2026, 5, 27), confirmed=False),
    ]


def test_closes_are_read_oldest_first_and_a_session_may_have_none():
    fetch = serve(ABC="closes.json")
    closes = bourse(fetch).closes("ABC", date(2026, 11, 2), date(2026, 11, 9))
    assert closes == [
        Close(date(2026, 11, 3), Decimal(50)),
        Close(date(2026, 11, 4), None),
        Close(date(2026, 11, 5), Decimal("51.95")),
        Close(date(2026, 11, 9), Decimal("52.4")),
    ]
    query = parse_qs(urlparse(fetch.asked[0]).query)
    assert (query["startDate"], query["endDate"]) == (["2026-11-02"], ["2026-11-09"])


def test_an_empty_answer_is_no_sessions():
    assert bourse(serve()).closes("ABC", date(2026, 11, 2), date(2026, 11, 9)) == []


def test_a_long_answer_is_read_page_by_page():
    fetch = serve(ABC_p1="page1.json", ABC_p2="page2.json")
    closes = bourse(fetch, page_size=2).closes("ABC", date(2026, 11, 2), date(2026, 11, 9))
    assert [c.session.day for c in closes] == [3, 4, 5]
    assert len(fetch.asked) == 2


def test_an_answer_in_another_shape_names_the_address(tmp_path):
    with pytest.raises(PriceSourceError, match="stock-historical.*shape"):
        bourse(lambda url: b'{"data": []}').closes("ABC", date(2026, 11, 2), date(2026, 11, 9))
    with pytest.raises(PriceSourceError, match="liste-emetteurs has no Drupal settings"):
        bourse(lambda url: b"<html></html>").listings()


def test_a_failed_request_names_the_address():
    def down(url: str) -> bytes:
        raise OSError("connection refused")

    with pytest.raises(PriceSourceError, match="stock-historical.*connection refused"):
        bourse(down).closes("ABC", date(2026, 11, 2), date(2026, 11, 9))


def test_every_answer_is_archived_as_given_and_reads_back(tmp_path):
    archive = RawArchive(tmp_path)
    source = bourse(serve(ABC="closes.json"), archive=archive)
    source.listings()
    closes = source.closes("ABC", date(2026, 11, 2), date(2026, 11, 9))
    [saved] = (tmp_path / "ABC").iterdir()
    assert saved.name == "20261110T183000000000Z_2026-11-02_2026-11-09_p1.json"
    assert saved.read_bytes() == (FIXTURES / "closes.json").read_bytes()
    assert [(t, at, sorted(c, key=lambda c: c.session)) for t, at, c in archive.closes()] == [
        ("ABC", AT, closes)
    ]
    assert [s.ticker for s in archive.latest_listings()] == ["ABC", "GAM"]


def test_the_bourse_s_missing_intermediate_is_trusted_and_checks_stay_on():
    context = tls_context()
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname
    names = {dict(rdn[0] for rdn in c["subject"]).get("commonName") for c in context.get_ca_certs()}
    assert "Sectigo Public Server Authentication CA DV R36" in names


def test_requests_are_spaced_out():
    waits: list[float] = []
    source = BourseCasablanca(fetch=serve(), pause=1.0, sleep=waits.append)
    source.listings()
    source.holidays()
    assert len(waits) == 1 and 0.9 < waits[0] <= 1.0


@pytest.mark.skipif(not (RECORDED / "IAM").is_dir(), reason="no real Bourse answers kept")
def test_bourse_replays_its_real_answers():
    archive = RawArchive(RECORDED)
    shares = archive.latest_listings()
    assert len(shares) >= 80 and any(s.ticker == "IAM" for s in shares)
    closes = [c for t, _, cs in archive.closes() if t == "IAM" for c in cs]
    assert len(closes) > 700 and all(c.close is not None for c in closes)
    assert json.loads((next((RECORDED / "IAM").iterdir())).read_bytes())["items"]
