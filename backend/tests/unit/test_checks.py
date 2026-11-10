"""The CHECKS queue (#23 AC1, AC2): a row per value a filing states for a figure that feeds a
KPI, problems first."""

from builders import BILLIONS, corrected, figure, rejected, review

from bloomberg_invest import config
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.service_layer.checks import queue_rows
from bloomberg_invest.views import DocumentRef

LABEL_MAP = config.label_map()
RULES = config.kpi_rules(LABEL_MAP)


def rows(facts, rejected=()):
    return queue_rows(facts, list(rejected), LABEL_MAP, RULES)


def test_only_consolidated_figures_that_feed_a_kpi_are_queued():
    queued = rows(
        [
            figure("36 681", "36681000000"),
            figure("36 681", "36681000000", scope=Scope.company_only),
            figure("1 000", "1000000000", breakdown="Mauritanie"),
            figure("5 275", "5275000000", line_item="share_capital"),
        ]
    )
    assert [(r.line_item, r.breakdown) for r in queued] == [("revenue", "")]
    [row] = queued
    assert (row.title, row.statement, row.status) == ("Revenue", "Income statement", "to_check")
    assert "Revenue growth" in row.feeds and "EV/Sales" in row.feeds


def test_a_value_stated_on_several_pages_is_one_row_shown_from_its_earliest_page():
    [row] = rows(
        [
            figure("36 681", "36681000000", page=24),
            figure("36,7", "36700000000", scale=BILLIONS, page=4),
            figure("36 681", "36681000000", page=40),
        ]
    )
    assert row.sources == 3
    assert len(row.figure_ids) == 3
    assert row.figure_ids[0] == "d1-revenue-2025-36,7-4"  # the one shown opens the viewer
    assert (row.value_as_written, row.passage.page, row.conflict) == ("36,7", 4, False)


def test_two_values_for_one_line_item_and_year_are_two_rows_marked_as_disagreeing():
    queued = rows(
        [
            figure("6 968", "6968000000", line_item="net_income"),
            figure("6 969", "6969000000", line_item="net_income", page=30),
        ]
    )
    assert [(r.value_as_written, r.conflict) for r in queued] == [("6 968", True), ("6 969", True)]


def test_each_filing_s_figures_are_checked_on_their_own():
    later = DocumentRef(
        **{**figure("1", "1").document.model_dump(), "id": "d2", "fiscal_year": 2026}
    )
    queued = rows(
        [figure("36 681", "36681000000"), figure("36 681", "36681000000", document=later)]
    )
    assert sorted(r.document.id for r in queued) == ["d1", "d2"]


def test_problems_come_first_then_statement_line_item_and_newest_year():
    queued = rows(
        [
            figure("90 000", "90000000000", line_item="total_assets"),
            figure("36 699", "36699000000", year=2024),
            figure("36 681", "36681000000"),
            figure("7 112", "7112000000", line_item="net_income"),
            figure("7 113", "7113000000", line_item="net_income", page=9),
        ],
        [rejected("18 002", line_item="equity", year=2023)],
    )
    assert [(r.line_item, r.fiscal_year, r.value_as_written) for r in queued] == [
        ("equity", 2023, "18 002"),  # rejected
        ("net_income", 2025, "7 112"),  # ≠
        ("net_income", 2025, "7 113"),
        ("revenue", 2025, "36 681"),  # income statement, before the balance sheet
        ("revenue", 2024, "36 699"),
        ("total_assets", 2025, "90 000"),
    ]


def test_rows_on_one_page_come_in_reading_order():
    lower = figure("7 112", "7112000000", line_item="net_income", top=400)
    higher = figure("7 113", "7113000000", line_item="net_income", top=120)
    for given in ([lower, higher], [higher, lower]):
        assert [r.value_as_written for r in rows(given)] == ["7 113", "7 112"]


def test_a_rejected_figure_needs_review_until_corrected():
    [row] = rows([], [rejected("18 002", line_item="equity")])
    assert (row.status, row.rejected, row.value) == (
        "rejected",
        "its value differs from its cell",
        None,
    )
    fixed = corrected("17 920", "17920000000")
    [row] = rows([], [rejected("18 002", line_item="equity", review=fixed)])
    assert (row.status, row.review.correction.value_as_written) == ("corrected", "17 920")


def test_a_row_is_done_once_every_figure_stating_it_is_checked():
    checked = review()
    partly = rows(
        [figure("36 681", "36681000000", review=checked), figure("36 681", "36681000000", page=9)]
    )
    assert [r.status for r in partly] == ["to_check"]
    done = rows(
        [
            figure("36 681", "36681000000", review=checked),
            figure("36 681", "36681000000", page=9, review=review(day=11)),
        ]
    )
    assert [(r.status, r.review.reviewed_at.day) for r in done] == [("accepted", 11)]
