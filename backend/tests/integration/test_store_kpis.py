"""The store's side of KPI values (#27, ADR 0002): each linked to its issuer, the Facts it read
and its compute Run; a recompute supersedes the values it replaces and keeps them. A check and
the KPI values it changes are written in one transaction."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from conftest import SHA, extract_income, make_run

from bloomberg_invest.domain.kpis import KpiChange, KpiResult, KpiStatus, TestResult, Used
from bloomberg_invest.domain.model import RunStep
from bloomberg_invest.domain.prices import XCAS, ListedShare
from bloomberg_invest.domain.review import ReviewDraft, Verdict

ISIN = "MA0000011488"


def compute_run(minute: int = 20):
    return make_run(minute).model_copy(
        update={"step": RunStep.compute, "tool": "bloomberg-invest", "output": None}
    )


def change(
    results: list[KpiResult],
    gone: list[tuple[str, int]] | None = None,
    minute: int = 20,
    isin: str = ISIN,
) -> KpiChange:
    return KpiChange(
        isin=isin,
        results=tuple(results),
        gone=tuple(gone or ()),
        run=compute_run(minute),
        rule_version="v1",
        rule_sha256="a" * 64,
        label_map="v1",
        superseded=0,
    )


def margin(value: str | None, sources: tuple[str, ...], year: int = 2025) -> KpiResult:
    return KpiResult(
        kpi="net_margin",
        fiscal_year=year,
        status=KpiStatus.computed if value else KpiStatus.unchecked,
        value=Decimal(value) if value else None,
        reason="" if value else "Waiting for check: Net income FY2025",
        used=(Used("net_income", year), Used("revenue", year)),
        sources=sources,
    )


@pytest.fixture
def figure_ids(store, document) -> list[str]:
    document_id, _ = document
    extract_income(store, document_id)
    facts, _ = store.figures(ISIN)
    return sorted(f.id for f in facts)


def test_kpi_values_are_kept_with_the_facts_they_read(store, figure_ids):
    run_id = store.record_kpi_values(change([margin("0.19", tuple(figure_ids))]))
    [stored] = store.kpi_values(ISIN)
    assert (stored.kpi, stored.fiscal_year, stored.status, stored.value) == (
        "net_margin",
        2025,
        KpiStatus.computed,
        "0.19",
    )
    assert (stored.rule_version, stored.rule_sha256, stored.label_map) == ("v1", "a" * 64, "v1")
    assert stored.sources == figure_ids
    assert [(u.name, u.fiscal_year) for u in stored.used] == [
        ("net_income", 2025),
        ("revenue", 2025),
    ]
    assert stored.computed_at == datetime(2026, 11, 3, 9, 24, tzinfo=UTC)
    assert run_id


def test_a_recompute_supersedes_the_values_it_replaces_and_keeps_them(store, figure_ids, driver):
    store.record_kpi_values(change([margin(None, ())], minute=20))
    store.record_kpi_values(change([margin("0.5", (), year=2024)], minute=21))
    run_id = store.record_kpi_values(change([margin("0.19", tuple(figure_ids))], minute=22))
    assert [(k.fiscal_year, k.value) for k in store.kpi_values(ISIN)] == [
        (2024, "0.5"),
        (2025, "0.19"),
    ]
    records, _, _ = driver.execute_query(
        "MATCH (k:KpiValue {superseded: true})-[:SUPERSEDED_BY]->(r:Run) "
        "RETURN k.value AS value, r.id AS run"
    )
    assert [(r["value"], r["run"]) for r in records] == [(None, run_id)]


def test_a_value_no_longer_computed_is_superseded_with_no_new_one(store, figure_ids):
    store.record_kpi_values(change([margin("0.19", ())], minute=20))
    store.record_kpi_values(change([], [("net_margin", 2025)], minute=21))
    assert store.kpi_values(ISIN) == []


def test_a_score_keeps_its_tests(store, figure_ids):
    score = KpiResult(
        kpi="f_score",
        fiscal_year=2025,
        status=KpiStatus.computed,
        value=Decimal(1),
        reason="",
        used=(),
        sources=(),
        tests=(
            TestResult("roa_positive", KpiStatus.computed, True, ""),
            TestResult("gross_margin_up", KpiStatus.not_meaningful, None, NO_GROSS_PROFIT),
        ),
        out_of=1,
    )
    store.record_kpi_values(change([score]))
    [stored] = store.kpi_values(ISIN)
    assert [(t.name, t.status, t.passed, t.reason) for t in stored.tests] == [
        ("roa_positive", KpiStatus.computed, True, ""),
        ("gross_margin_up", KpiStatus.not_meaningful, None, NO_GROSS_PROFIT),
    ]
    assert stored.out_of == 1


NO_GROSS_PROFIT = "Not meaningful: the income statement is by nature: no gross profit"


def test_kpi_values_of_an_unknown_issuer_are_refused(store):
    with pytest.raises(LookupError):
        store.record_kpi_values(change([], isin="MA0000000000"))


def test_kpi_values_whose_source_is_no_figure_are_refused_and_nothing_is_kept(
    store, figure_ids, driver
):
    with pytest.raises(LookupError, match="1 of the KPI values' sources"):
        store.record_kpi_values(change([margin("0.19", (figure_ids[0], "nope"))]))
    assert store.kpi_values(ISIN) == []
    records, _, _ = driver.execute_query("MATCH (r:Run {step: 'compute'}) RETURN r")
    assert records == []


def test_kpi_values_whose_source_a_re_extract_superseded_are_refused(store, document, figure_ids):
    document_id, _ = document
    extract_income(store, document_id, minute=30)
    with pytest.raises(LookupError, match="2 of the KPI values' sources"):
        store.record_kpi_values(change([margin("0.19", tuple(figure_ids[:2]))]))
    assert store.kpi_values(ISIN) == []


def check() -> ReviewDraft:
    return ReviewDraft(Verdict.accepted, "Z. Bajjou", datetime(2026, 11, 10, 9, 30, tzinfo=UTC))


def test_a_check_and_the_kpi_values_it_changes_are_written_together(store, figure_ids):
    review_id = store.record_review(
        figure_ids[:1], check(), [change([margin("0.19", tuple(figure_ids))])]
    )
    [stored] = store.kpi_values(ISIN)
    assert stored.value == "0.19"
    checked = store.figure(figure_ids[0])
    assert checked.review is not None and checked.review.id == review_id


def test_a_check_whose_kpi_values_fail_is_not_kept(store, figure_ids):
    with pytest.raises(LookupError):
        store.record_review(figure_ids[:1], check(), [change([margin("0.19", ("nope",))])])
    assert store.kpi_values(ISIN) == []
    assert store.figure(figure_ids[0]).review is None


def test_a_sector_s_kpi_values_are_those_of_the_other_companies_listed_in_it(
    store, figure_ids, meta, parsed
):

    other = meta.model_copy(
        update={"issuer": meta.issuer.model_copy(update={"isin": "MA0000012445"})}
    )
    store.record_parse(other, parsed, make_run(), SHA.replace("9", "8"))
    telecom = ListedShare("IAM", "ITISSALAT AL-MAGHRIB", "Télécommunications", "Principal A")
    peer = ListedShare("OTH", "OTHER TELECOM", "Télécommunications", "Principal A")
    store.upsert_listings(
        XCAS, [telecom, peer], {"IAM": ISIN, "OTH": "MA0000012445"}, datetime.now(UTC)
    )
    store.record_kpi_values(change([margin("0.19", ())]))
    store.record_kpi_values(
        change([margin("0.3", ()), margin("0.2", (), 2024)], isin="MA0000012445")
    )
    peers = store.sector_kpi_values("Télécommunications", 2025, other_than=ISIN)
    assert [(k.kpi, k.fiscal_year, k.value) for k in peers] == [("net_margin", 2025, "0.3")]
    assert store.sector_kpi_values("Banques", 2025, other_than=ISIN) == []
