"""The dossier's figure grid (#19 R19): rows by the label map, values that agree grouped."""

from builders import BILLIONS, MILLIONS, figure

from bloomberg_invest import config
from bloomberg_invest.domain.figures import Scope
from bloomberg_invest.service_layer.company import figure_grid
from bloomberg_invest.views import Figure


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
