"""The dossier's figure grid (#19 R19): rows by the label map, values that agree grouped."""

from datetime import date

from builders import BILLIONS, MILLIONS, corrected, figure, rejected, review

from bloomberg_invest import config
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.service_layer.company import as_shown, figure_grid, flagged
from bloomberg_invest.views import Figure, Passage

LABEL_MAP = config.label_map()
RULES = config.kpi_rules(LABEL_MAP)


def consolidated(figures: list[Figure]):
    return next(
        s for s in figure_grid(figures, config.label_map()).scopes if s.scope == "consolidated"
    )


def test_rows_follow_the_label_map_and_years_run_newest_first():
    grid = consolidated(
        [
            figure("7 112", "7112000000", line_item="net_income"),
            figure("36 699", "36699000000", year=2024),
            figure("36 681", "36681000000"),
        ]
    )

    assert grid.years == [2025, 2024]
    [income] = grid.statements
    assert [r.line_item for r in income.rows] == ["revenue", "net_income"]
    assert [y.fiscal_year for y in income.rows[0].years] == [2025, 2024]


def test_a_rounded_statement_joins_the_exact_one_shown_in_the_rows_unit():
    exact = figure("36 681", "36681000000", page=40)
    rounded = figure("36,7", "36700000000", scale=BILLIONS, page=3)
    again = figure("36 681", "36681000000", page=50)

    [row] = consolidated([rounded, exact, again]).statements[0].rows

    assert (row.unit, row.scale) == ("MAD", MILLIONS)
    [value] = row.years[0].values
    assert value.shown == exact  # the row's unit before the earlier, rounded page
    assert value.sources == [exact, again, rounded]


def test_a_value_the_filing_states_differently_is_a_second_value():
    [row] = (
        consolidated([figure("6 969", "6969000000"), figure("6 968", "6968000000", page=9)])
        .statements[0]
        .rows
    )

    assert [v.shown.value_as_written for v in row.years[0].values] == ["6 969", "6 968"]


def test_another_currency_and_a_breakdown_are_rows_of_their_own_after_the_line_item():
    rows = (
        consolidated(
            [
                figure("3 345", "3345000000", currency="EUR"),
                figure("21 000", "21000000000", breakdown="Maroc"),
                figure("36 681", "36681000000"),
                figure("15 681", "15681000000", breakdown="International"),
            ]
        )
        .statements[0]
        .rows
    )

    assert [(r.currency, r.breakdown) for r in rows] == [
        ("MAD", ""),
        ("MAD", "International"),
        ("MAD", "Maroc"),
        ("EUR", ""),
    ]


def test_each_basis_has_its_own_years_and_the_count_covers_both():
    grid = figure_grid(
        [
            figure("36 681", "36681000000"),
            figure("10 000", "10000000000", year=2023, scope=Scope.company_only),
        ],
        config.label_map(),
    )

    assert grid.count == 2
    assert [(s.scope, s.years) for s in grid.scopes] == [
        ("consolidated", [2025]),
        ("company-only", [2023]),
    ]


def test_a_line_item_the_label_map_no_longer_has_is_left_out_and_not_counted():
    retired = [figure("1", "1000000", line_item="retired_item"), figure("36 681", "36681000000")]
    grid = figure_grid(retired, config.label_map())

    assert grid.count == 1
    assert [r.line_item for r in grid.scopes[0].statements[0].rows] == ["revenue"]


def test_a_figure_needs_review_until_checked_and_only_when_it_feeds_a_kpi():
    assert flagged(figure("36 681", "36681000000"), RULES).needs_review
    assert not flagged(figure("36 681", "36681000000", review=review()), RULES).needs_review
    assert not flagged(figure("5 275", "5275000000", line_item="share_capital"), RULES).needs_review
    company_only = figure("36 681", "36681000000", scope=Scope.company_only)
    assert not flagged(company_only, RULES).needs_review


def test_an_unchecked_or_accepted_figure_shows_what_it_read():
    read = figure("36 681", "36681000000")
    assert as_shown(read, LABEL_MAP) == read
    accepted = figure("36 681", "36681000000", review=review())
    assert as_shown(accepted, LABEL_MAP) == accepted


def test_a_corrected_figure_shows_its_correction_from_the_cell_picked():
    cell = Passage(kind="cell", page=24, boxes=[], text="36 680")
    read = figure("36 681", "36681000000", review=corrected("36 680", "36680000000", source=cell))
    shown = as_shown(read, LABEL_MAP)
    assert (shown.value_as_written, shown.value, shown.passage, shown.page) == (
        "36 680",
        "36680000000",
        cell,
        24,
    )


def test_a_typed_correction_shows_where_the_figure_was_read():
    read = figure("36 681", "36681000000", review=corrected("36 680", "36680000000"))
    shown = as_shown(read, LABEL_MAP)
    assert (shown.value_as_written, shown.passage, shown.page) == ("36 680", read.passage, 4)


def test_a_rejected_figure_joins_the_dossier_once_corrected():
    assert as_shown(rejected("18 002", line_item="equity"), LABEL_MAP) is None
    typed = rejected("18 002", line_item="equity", review=corrected("17 920", "17920000000"))
    shown = as_shown(typed, LABEL_MAP)
    assert (shown.value_as_written, shown.value, shown.unit, shown.scale) == (
        "17 920",
        "17920000000",
        "MAD",
        MILLIONS,
    )
    assert (shown.passage, shown.page) == (None, 26)  # the page the figure was read on
    assert (shown.as_of, shown.period_start) == (date(2025, 12, 31), None)  # equity is a stock
    assert shown.basis_standard == "IFRS"
    in_grid = consolidated([shown]).statements[0].rows[0].years[0].values[0].shown
    assert in_grid.value_as_written == "17 920"


def test_a_checked_value_is_shown_before_the_others():
    unchecked = figure("36 681", "36681000000", page=4)
    checked = figure("36 680", "36680000000", page=24, review=review())
    [year] = consolidated([unchecked, checked]).statements[0].rows[0].years
    assert [v.shown.value_as_written for v in year.values] == ["36 680", "36 681"]


def test_a_checked_figure_is_shown_for_its_value():
    earliest = figure("36 681", "36681000000", page=4)
    checked = figure("36 681", "36681000000", page=9, review=review())
    [year] = consolidated([earliest, checked]).statements[0].rows[0].years
    [value] = year.values
    assert (value.shown.page, len(value.sources)) == (9, 2)


def test_a_value_partly_checked_is_neither_first_nor_unflagged():
    # A re-extract kept the check of one of the two figures stating 36 681.
    partly = [
        flagged(figure("36 681", "36681000000", page=4, review=review()), RULES),
        flagged(figure("36 681", "36681000000", page=9), RULES),
    ]
    checked = flagged(figure("36 680", "36680000000", page=24, review=review()), RULES)
    [year] = consolidated([*partly, checked]).statements[0].rows[0].years
    assert [v.shown.value_as_written for v in year.values] == ["36 680", "36 681"]
    assert [v.shown.needs_review for v in year.values] == [False, True]
