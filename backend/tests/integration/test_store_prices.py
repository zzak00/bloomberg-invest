"""The GraphStore contract for Listings and daily closes (#26 AC1, AC3)."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from bloomberg_invest.domain.prices import MANUAL, XCAS, Close, ListedShare, StoredClose
from bloomberg_invest.views import Listing

IAM = ListedShare("IAM", "ITISSALAT AL-MAGHRIB", "Télécommunications", "Principal A")
ATW = ListedShare("ATW", "ATTIJARIWAFA BANK", "Banques", "Principal A")
AT = datetime(2026, 11, 10, 18, 30, tzinfo=UTC)
LATER = datetime(2026, 11, 11, 18, 30, tzinfo=UTC)
SOURCE = "bourse-casablanca"


def closes(*pairs: tuple[int, str | None]) -> list[Close]:
    return [Close(date(2026, 11, d), None if v is None else Decimal(v)) for d, v in pairs]


def test_a_listing_links_to_the_organisation_its_isin_names(store, document):
    assert store.upsert_listings(XCAS, [IAM, ATW], {"IAM": "MA0000011488"}, AT) == []
    assert store.listing("MA0000011488") == Listing(
        ticker="IAM",
        mic=XCAS,
        name="ITISSALAT AL-MAGHRIB",
        sector="Télécommunications",
        compartment="Principal A",
    )
    assert store.tickers(XCAS) == ["ATW", "IAM"]


def test_a_share_no_longer_listed_keeps_its_listing_and_is_reported(store):
    store.upsert_listings(XCAS, [IAM, ATW], {}, AT)
    assert store.upsert_listings(XCAS, [IAM], {}, LATER) == ["ATW"]
    assert store.tickers(XCAS) == ["ATW", "IAM"]


def test_closes_are_stored_once_per_session_and_source(store):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    assert (
        store.add_prices(
            "XCAS:IAM", closes((3, "88.9"), (4, None), (5, "88.95")), SOURCE, "MAD", AT
        )
        == 2
    )
    assert (
        store.add_prices(
            "XCAS:IAM", closes((3, "88.9"), (5, "88.95"), (9, "89.8")), SOURCE, "MAD", LATER
        )
        == 1
    )
    assert [(c.session.day, c.close) for c in store.prices("XCAS:IAM")] == [
        (3, Decimal("88.9")),
        (5, Decimal("88.95")),
        (9, Decimal("89.8")),
    ]
    assert store.last_session("XCAS:IAM", SOURCE) == date(2026, 11, 9)


def test_a_later_different_close_supersedes_the_stored_one(store, driver):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    store.add_prices("XCAS:IAM", closes((5, "88.95")), SOURCE, "MAD", AT)
    assert store.add_prices("XCAS:IAM", closes((5, "90")), SOURCE, "MAD", LATER) == 1
    assert store.prices("XCAS:IAM") == [StoredClose(date(2026, 11, 5), Decimal(90), SOURCE, "MAD")]
    records, _, _ = driver.execute_query(
        "MATCH (old:Price {close: '88.95'})-[:SUPERSEDED_BY]->(new:Price) "
        "RETURN old.superseded AS gone, new.close AS close"
    )
    assert [(r["gone"], r["close"]) for r in records] == [(True, "90")]


def test_an_older_answer_never_undoes_a_newer_close(store):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    store.add_prices("XCAS:IAM", closes((5, "90")), SOURCE, "MAD", LATER)
    assert store.add_prices("XCAS:IAM", closes((5, "88.95")), SOURCE, "MAD", AT) == 0
    assert store.add_prices("XCAS:IAM", closes((5, "90")), SOURCE, "MAD", LATER) == 0
    assert [c.close for c in store.prices("XCAS:IAM")] == [Decimal(90)]


def test_the_same_close_written_another_way_is_the_same(store):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    store.add_prices("XCAS:IAM", closes((5, "88.90")), SOURCE, "MAD", AT)
    assert store.add_prices("XCAS:IAM", closes((5, "88.9")), SOURCE, "MAD", LATER) == 0


def test_a_manual_close_sits_beside_the_exchange_s_and_since_filters(store):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    store.add_prices("XCAS:IAM", closes((3, "88.9"), (5, "88.95")), SOURCE, "MAD", AT)
    store.add_prices("XCAS:IAM", closes((5, "88.8")), MANUAL, "MAD", LATER)
    assert [
        (c.session.day, c.source) for c in store.prices("XCAS:IAM", since=date(2026, 11, 4))
    ] == [
        (5, SOURCE),
        (5, MANUAL),
    ]
    assert store.last_session("XCAS:IAM", MANUAL) == date(2026, 11, 5)
    assert store.last_session("XCAS:ATW", SOURCE) is None


def test_a_company_with_no_listing_has_none(store, document):
    assert store.listing("MA0000011488") is None


def test_a_company_with_two_listings_always_shows_the_first_by_key(store, document):
    paris = ListedShare("IAM", "MAROC TELECOM", "Télécommunications", "Euronext")
    store.upsert_listings("XPAR", [paris], {"IAM": "MA0000011488"}, AT)
    store.upsert_listings(XCAS, [IAM], {"IAM": "MA0000011488"}, AT)
    assert [store.listing("MA0000011488").mic for _ in range(3)] == ["XCAS"] * 3


def test_runs_writing_one_share_at_once_leave_one_current_close(store):
    store.upsert_listings(XCAS, [IAM], {}, AT)
    store.add_prices("XCAS:IAM", closes((5, "88")), SOURCE, "MAD", AT)

    def write(n: int) -> int:
        later = AT + timedelta(seconds=n + 1)
        return store.add_prices("XCAS:IAM", closes((5, f"9{n}")), SOURCE, "MAD", later)

    with ThreadPoolExecutor(8) as pool:
        list(pool.map(write, range(8)))
    assert len(store.prices("XCAS:IAM")) == 1
