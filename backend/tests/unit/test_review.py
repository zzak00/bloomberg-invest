"""Which figures need a check, how a correction is read, and when a check carries over
(#19 R4, R9, R10)."""

import pytest

from bloomberg_invest import config
from bloomberg_invest.domain.kpis import Input, Kpi, KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import (
    InvalidCorrection,
    Reading,
    carried,
    correction,
    needs_review,
    numbers_in,
)

RULES = config.kpi_rules()


def test_the_kpi_rules_name_only_line_items_of_the_label_map():
    rules = config.kpi_rules()
    assert rules.version == "v1"
    assert len(rules.sha256) == 64
    inputs = {i.line_item for kpi in rules.kpis.values() for i in kpi.inputs}
    assert inputs <= set(config.label_map().items)


def test_kpi_rules_naming_an_unknown_line_item_fail():
    rules = KpiRules("v9", "0" * 64, {"x": Kpi("x", "X", (Input("gross_profit"),))})
    with pytest.raises(ValueError, match="'gross_profit', which label map v1 does not have"):
        rules.check_against(config.label_map())


def test_a_line_item_feeds_the_kpis_that_read_it():
    assert RULES.feeds("current_assets", "") == ["Current ratio", "Piotroski F-score"]
    assert "P/E" in RULES.feeds("eps", "basic")
    assert RULES.feeds("eps", "diluted") == []
    assert RULES.feeds("share_capital", "") == []


@pytest.mark.parametrize(
    ("scope", "line_item", "breakdown", "needed"),
    [
        ("consolidated", "revenue", "", True),
        ("consolidated", "eps", "basic", True),
        ("company-only", "revenue", "", False),  # KPIs read consolidated IFRS only (#7)
        ("consolidated", "revenue", "Mauritanie", False),  # a segment feeds no KPI
        ("consolidated", "share_capital", "", False),
        (None, "revenue", "", False),
    ],
)
def test_only_consolidated_kpi_inputs_need_a_check(scope, line_item, breakdown, needed):
    assert needs_review(scope, line_item, breakdown, RULES) is needed


def test_a_correction_is_parsed_like_an_extracted_value():
    fixed = correction(" 11 904 ", "MAD millions")
    assert (fixed.value_as_written, fixed.value) == ("11 904", "11904000000")
    assert (fixed.unit, fixed.scale, fixed.currency) == ("MAD", 1_000_000, "MAD")
    assert correction("4,00", "MAD per share").value == "4"


@pytest.mark.parametrize(
    ("written", "unit", "message"),
    [
        ("11 904 ou 11 940", "MAD millions", "is not one number"),
        ("", "MAD millions", "is not one number"),
        ("11 904", "units", "names nothing countable"),
    ],
)
def test_an_unreadable_correction_says_why(written, unit, message):
    with pytest.raises(InvalidCorrection, match=message):
        correction(written, unit)


def test_a_paragraph_offers_each_whole_number_once():
    paragraph = (
        "Le chiffre d'affaires atteint 36 681 MDH en 2025, contre 36 699 MDH en 2024 ; "
        "le dividende proposé est de 4,00 dirhams, soit 36 681 au total."
    )
    assert numbers_in(paragraph) == ["36 681", "2025", "36 699", "2024", "4,00"]


def test_numbers_side_by_side_in_a_flat_row_are_two():
    assert numbers_in("Chiffre d'affaires 36 699 36 681 -988") == ["36 699", "36 681", "-988"]


def reading(value: str = "36 681", **changes) -> Reading:
    fields = {
        "line_item": "revenue",
        "fiscal_year": 2025,
        "basis_scope": "consolidated",
        "breakdown": "",
        "value_as_written": value,
        "unit_as_written": "MAD millions",
        "source": ("cell", 24, 3, 1, 3),
    } | changes
    return Reading(**fields)


def test_a_check_carries_over_only_to_the_same_value_from_the_same_source():
    earlier = [(reading(), "check-revenue"), (reading("7 112", line_item="net_income"), "check-ni")]
    later = [
        (reading(), "new-revenue"),  # same value, same cell: kept
        (reading("7 121", line_item="net_income"), "new-ni"),  # value changed: back to CHECKS
        (reading(source=("cell", 24, 3, 1, 2)), "other-cell"),  # another cell: back to CHECKS
        (reading(fiscal_year=2024), "other-year"),
    ]
    assert carried(earlier, later) == [("check-revenue", "new-revenue")]


def test_a_quoted_figure_carries_over_by_page_quote_and_paragraph():
    span = ("span", 10, "4,00", "Le dividende proposé est de 4,00 dirhams.")
    earlier = [(reading("4,00", source=span), "check")]
    assert carried(earlier, [(reading("4,00", source=span), "new")]) == [("check", "new")]
    moved = ("span", 10, "4,00", "Le dividende proposé reste de 4,00 dirhams.")
    assert carried(earlier, [(reading("4,00", source=moved), "new")]) == []


def test_an_empty_label_map_is_not_a_kpi_source():
    empty = LabelMap("v0", "0" * 64, {}, {})
    with pytest.raises(ValueError, match="label map v0 does not have"):
        config.kpi_rules(against=empty)
