"""The store's side of CHECKS (#23 AC1, AC3, AC4): Reviews recorded and read with every figure,
and carried over to a re-extracted figure only when it reads the same value from the same cell."""

from datetime import UTC, datetime

import pytest
from conftest import INCOME_ANSWER, SHA, extract_income, make_run

from bloomberg_invest.domain.extraction import SourceParagraph
from bloomberg_invest.domain.review import (
    Correction,
    QuotedSource,
    ReviewDraft,
    Verdict,
    check_of,
    correction,
)

ISIN = "MA0000011488"


def check(verdict: Verdict = Verdict.accepted, minute: int = 30, **fields) -> ReviewDraft:
    return ReviewDraft(
        verdict=verdict,
        reviewer="Z. Bajjou",
        reviewed_at=datetime(2026, 11, 10, 9, minute, tzinfo=UTC),
        **fields,
    )


def fixed(value: str) -> Correction:
    return correction(value, "MAD millions")


@pytest.fixture
def extracted(store, document):
    document_id, _ = document
    extract_income(store, document_id)
    return document_id


def figures_by_value(store):
    facts, rejected = store.figures(ISIN)
    return {f.value_as_written: f for f in [*facts, *rejected]}


def test_figures_are_the_current_facts_and_rejected_figures(store, extracted):
    facts, rejected = store.figures()
    assert sorted(f.value_as_written for f in facts) == ["36 681", "36 699"]
    [misread] = rejected
    assert (misread.value_as_written, misread.reason) == (
        "7 121",
        "its value differs from its cell",
    )
    assert (misread.page, misread.passage.text, misread.unit_as_written) == (
        2,
        "7 112",
        "MAD millions",
    )
    assert all(f.review is None for f in [*facts, *rejected])
    assert [f.page for f in facts] == [2, 2]
    assert store.figures("MA0000000000") == ([], [])
    only = store.figures(ids=[facts[0].id])
    assert [f.id for f in only[0]] == [facts[0].id] and only[1] == []


def test_an_accepted_figure_reads_with_its_check_everywhere(store, extracted, driver):
    revenue = figures_by_value(store)["36 681"]
    review_id = store.record_review([revenue.id], check())

    [read] = [f for f in store.figures(ISIN)[0] if f.id == revenue.id]
    assert (read.review.id, read.review.verdict, read.review.reviewer) == (
        review_id,
        "accepted",
        "Z. Bajjou",
    )
    assert read.review.reviewed_at == datetime(2026, 11, 10, 9, 30, tzinfo=UTC)
    assert store.figure(revenue.id).review.id == review_id
    assert read.review.source is None
    other = figures_by_value(store)["36 699"]
    assert other.review is None
    records, _, _ = driver.execute_query(
        "MATCH (rv:Review {id: $id})-[:REVIEWS]->(n) RETURN n.id AS id", id=review_id
    )
    assert [r["id"] for r in records] == [revenue.id]


def test_one_check_reviews_every_figure_of_a_row(store, extracted, driver):
    by_value = figures_by_value(store)
    ids = [by_value["36 681"].id, by_value["36 699"].id]
    review_id = store.record_review(ids, check())
    records, _, _ = driver.execute_query(
        "MATCH (:Review {id: $id})-[:REVIEWS]->(n) RETURN count(n) AS n", id=review_id
    )
    assert records[0]["n"] == 2


def test_a_correction_keeps_the_right_value_and_the_cell_picked(store, extracted, driver):
    misread = figures_by_value(store)["7 121"]
    [cell] = [c for c in store.row_cells(misread.id) if c.value_as_written == "7 112"]
    review_id = store.record_review(
        [misread.id], check(Verdict.corrected, correction=fixed("7 112"), cell_id=cell.cell_id)
    )
    corrected = figures_by_value(store)["7 121"].review
    assert (corrected.verdict, corrected.correction) == ("corrected", fixed("7 112"))
    assert (corrected.source.kind, corrected.source.text) == ("cell", "7 112")
    assert store.figure(misread.id).review == corrected
    records, _, _ = driver.execute_query(
        "MATCH (:Review {id: $id})-[:CITES]->(c:Cell:Passage) RETURN c.text AS text", id=review_id
    )
    assert [r["text"] for r in records] == ["7 112"]
    # The figure itself never changes (#19 R4).
    assert figures_by_value(store)["7 121"].value_as_written == "7 121"


def test_a_correction_picked_in_a_paragraph_cites_a_span_of_its_own(store, extracted, driver):
    revenue = figures_by_value(store)["36 681"]
    quoted = QuotedSource(
        page=2,
        quote="36 680",
        text="Le chiffre d'affaires atteint 36 680 MDH.",
        boxes=((2, 100.0, 300.0, 140.0, 312.0),),
    )
    review_id = store.record_review(
        [revenue.id], check(Verdict.corrected, correction=fixed("36 680"), quoted=quoted)
    )
    records, _, _ = driver.execute_query(
        """
        MATCH (:Review {id: $id})-[:CITES]->(s:Span:Passage)-[:ON_PAGE]->(p:Page)
        RETURN s, p.number AS page, EXISTS { (s)-[:PRODUCED_BY]->() } AS produced
        """,
        id=review_id,
    )
    [r] = records
    assert (r["s"]["quote"], r["s"]["boxes_from"], r["page"], r["produced"]) == (
        "36 680",
        "quote",
        2,
        False,
    )
    assert r["s"]["boxes"] == [2.0, 100.0, 300.0, 140.0, 312.0]
    source = figures_by_value(store)["36 681"].review.source
    assert (source.kind, source.page, source.quote) == ("span", 2, "36 680")


def test_reopening_undoes_the_check_without_deleting_it(store, extracted, driver):
    revenue = figures_by_value(store)["36 681"]
    store.record_review([revenue.id], check())
    store.record_review([revenue.id], check(Verdict.reopened, minute=31))
    assert figures_by_value(store)["36 681"].review is None
    records, _, _ = driver.execute_query("MATCH (rv:Review) RETURN count(rv) AS n")
    assert records[0]["n"] == 2


def test_a_check_needs_current_figures(store, extracted):
    with pytest.raises(LookupError, match="current figures"):
        store.record_review(["nope"], check())
    with pytest.raises(LookupError, match="current figures"):
        store.record_review([], check())


def test_a_figure_s_row_offers_its_cells_with_their_column_headers(store, extracted):
    misread = figures_by_value(store)["7 121"]
    assert [(c.value_as_written, c.context) for c in store.row_cells(misread.id)] == [
        ("Résultat net", "(En millions MAD)"),
        ("6 968", "31-déc.-24"),
        ("7 112", "31-déc.-25"),
    ]


def test_re_extracting_keeps_a_check_only_on_the_same_value_from_the_same_cell(
    store, extracted, driver
):
    by_value = figures_by_value(store)
    kept = store.record_review([by_value["36 681"].id], check())
    store.record_review([by_value["36 699"].id], check(minute=31))

    # The model now reads revenue 2024 from net income's row: another cell, back to CHECKS.
    answer = [INCOME_ANSWER[0], ("revenue", 2024, "t2.0.r2.c1", "6 968"), INCOME_ANSWER[2]]
    extract_income(store, extracted, answer, minute=20)

    again = figures_by_value(store)
    assert again["36 681"].id != by_value["36 681"].id  # a new Fact, the old one superseded
    assert again["36 681"].review.id == kept
    # The old figure stays in the graph, superseded, and keeps its check (#19 R4).
    records, _, _ = driver.execute_query(
        """
        MATCH (:Review {id: $kept})-[:REVIEWS]->(n:Fact)
        RETURN n.id AS id, coalesce(n.superseded, false) AS superseded ORDER BY superseded
        """,
        kept=kept,
    )
    assert [(r["id"], r["superseded"]) for r in records] == [
        (again["36 681"].id, False),
        (by_value["36 681"].id, True),
    ]
    assert again["6 968"].review is None
    assert again["7 121"].review is None


def test_a_changed_value_from_the_same_cell_goes_back_to_checks(store, extracted):
    revenue = figures_by_value(store)["36 681"]
    store.record_review([revenue.id], check())
    misread = [("revenue", 2025, "t2.0.r1.c2", "36 68"), *INCOME_ANSWER[1:]]
    extract_income(store, extracted, misread, minute=20)
    assert "36 681" not in figures_by_value(store)
    assert figures_by_value(store)["36 68"].review is None


def test_a_check_survives_a_re_parse_that_keeps_the_cell_where_it_was(
    store, extracted, meta, parsed
):
    revenue = figures_by_value(store)["36 681"]
    kept = store.record_review([revenue.id], check())
    store.record_parse(meta, parsed, make_run(15), SHA)  # new Cells, the old figures superseded
    assert store.figures(ISIN) == ([], [])
    extract_income(store, extracted, minute=20)
    assert figures_by_value(store)["36 681"].review.id == kept


def test_a_reopened_check_does_not_come_back_on_re_extract(store, extracted):
    revenue = figures_by_value(store)["36 681"]
    store.record_review([revenue.id], check())
    store.record_review([revenue.id], check(Verdict.reopened, minute=31))
    extract_income(store, extracted, minute=20)
    assert figures_by_value(store)["36 681"].review is None


def test_only_the_previous_run_s_checks_carry_over(store, extracted):
    revenue = figures_by_value(store)["36 681"]
    store.record_review([revenue.id], check())
    misread = [("revenue", 2025, "t2.0.r1.c2", "36 68"), *INCOME_ANSWER[1:]]
    extract_income(store, extracted, misread, minute=20)  # read differently: back to CHECKS
    extract_income(store, extracted, minute=25)  # read as first again: still unchecked
    assert figures_by_value(store)["36 681"].review is None


def test_a_figure_with_no_passage_never_carries_its_check_over(store, extracted):
    # The model cites an id the page does not have: the figure has no Passage to check against.
    answer = [*INCOME_ANSWER, ("net_income", 2024, "t9.9.r9.c9", "6 968")]
    extract_income(store, extracted, answer, minute=15)
    unsourced = figures_by_value(store)["6 968"]
    assert unsourced.passage is None
    store.record_review([unsourced.id], check(Verdict.corrected, correction=fixed("6 968")))
    extract_income(store, extracted, answer, minute=20)
    again = figures_by_value(store)["6 968"]
    assert again.id != unsourced.id
    assert again.review is None


def test_a_value_whose_check_carried_over_in_part_has_no_check(store, extracted):
    def income(text: str, minute: int):
        paragraph = SourceParagraph(page=2, text=text, boxes=((2, 50.0, 220.0, 545.0, 240.0),))
        answer = [INCOME_ANSWER[0], ("revenue", 2025, "p2.0", "36 681")]
        extract_income(store, extracted, answer, minute=minute, paragraphs=(paragraph,))

    income("Le chiffre d'affaires atteint 36 681 MDH.", minute=15)
    facts, _ = store.figures(ISIN)
    store.record_review([f.id for f in facts], check())
    # The cell reads the same; the paragraph does not, so its figure goes back to CHECKS.
    income("Le chiffre d'affaires consolidé atteint 36 681 MDH.", minute=20)
    facts, _ = store.figures(ISIN)
    assert sorted(f.review is None for f in facts) == [False, True]
    assert check_of([f.review for f in facts]) is None
