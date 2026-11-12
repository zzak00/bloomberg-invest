"""Which figures need a check, how a correction is read, and when a check carries over
(#19 R4, R9, R10)."""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from builders import BILLIONS, DOCUMENT, figure, review

from bloomberg_invest import config
from bloomberg_invest.domain.kpis import Input, Kpi, KpiRules
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.review import (
    CheckStatus,
    InvalidCorrection,
    Reading,
    Verdict,
    around,
    carried,
    check_of,
    correction,
    correction_in_force,
    covering,
    fact_key,
    fact_status,
    needs_check,
    numbers_in,
    refusal,
    rejected_key,
    rejected_status,
    value_check,
)

RULES = config.kpi_rules(config.label_map())


def test_the_kpi_rules_name_only_line_items_of_the_label_map():
    rules = config.kpi_rules(config.label_map())
    assert rules.version == "v1"
    assert len(rules.sha256) == 64
    inputs = {i.line_item for kpi in rules.kpis for i in kpi.inputs}
    assert inputs <= set(config.label_map().items)


def test_kpi_rules_naming_an_unknown_line_item_fail():
    rules = KpiRules("v9", "0" * 64, (Kpi("x", "X", (Input("gross_profit"),)),))
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
    figure = SimpleNamespace(basis_scope=scope, line_item=line_item, breakdown=breakdown)
    assert needs_check(figure, RULES) is needed


def test_a_reopening_leaves_no_check_in_force():
    assert Verdict.accepted.in_force and Verdict.corrected.in_force
    assert not Verdict.reopened.in_force


def test_only_a_correction_gives_a_value_in_force():
    fixed = correction("36 680", "MAD millions")
    corrected = SimpleNamespace(verdict=Verdict.corrected, correction=fixed)
    assert correction_in_force(corrected) == (corrected, fixed)
    assert correction_in_force(SimpleNamespace(verdict=Verdict.accepted, correction=None)) is None
    assert correction_in_force(None) is None


def test_a_value_is_checked_once_every_figure_stating_it_is():
    early = SimpleNamespace(reviewed_at=datetime(2026, 11, 10, 9, tzinfo=UTC))
    late = SimpleNamespace(reviewed_at=datetime(2026, 11, 10, 10, tzinfo=UTC))
    assert check_of([early, late]) is late
    assert check_of([early, None]) is None  # a re-extract kept only one check
    assert check_of([]) is None


def test_a_row_s_status_follows_its_check():
    accepted = SimpleNamespace(verdict=Verdict.accepted)
    corrected = SimpleNamespace(verdict=Verdict.corrected)
    assert fact_status(None) == CheckStatus.to_check
    assert rejected_status(None) == CheckStatus.rejected
    assert fact_status(accepted) == CheckStatus.accepted
    assert rejected_status(corrected) == CheckStatus.corrected


def test_a_correction_states_the_fields_a_figure_shows():
    assert correction("36 680", "MAD millions").stated() == {
        "value_as_written": "36 680",
        "unit_as_written": "MAD millions",
        "value": "36680000000",
        "unit": "MAD",
        "scale": 1_000_000,
        "currency": "MAD",
    }


def fact(value: str = "36 681", **changes):
    fields = {
        "document": SimpleNamespace(id="d1"),
        "line_item": "revenue",
        "fiscal_year": 2025,
        "basis_scope": "consolidated",
        "breakdown": "",
        "value_as_written": value,
        "value": str(int(value.replace(" ", "")) * 1_000_000),
        "scale": 1_000_000,
        "unit": "MAD",
        "currency": "MAD",
    } | changes
    return SimpleNamespace(**fields)


def test_one_check_covers_a_line_item_year_basis_and_currency_of_one_filing():
    assert fact_key(fact()) == fact_key(fact(value="36 681"))
    assert fact_key(fact()) != fact_key(fact(currency="EUR"))
    assert fact_key(fact(currency=None, unit="%")).currency == "%"
    assert rejected_key(fact()).currency == ""


@pytest.mark.parametrize(
    ("facts", "rejected", "verdict", "reason"),
    [
        ([], [], Verdict.accepted, "names the figures"),
        ([fact(line_item="share_capital")], [], Verdict.accepted, "needs no check"),
        ([fact(), fact(fiscal_year=2024)], [], Verdict.accepted, "One check covers"),
        ([], [fact(), fact()], Verdict.corrected, "checked on its own"),
        ([fact(), fact("36 680")], [], Verdict.accepted, "different values"),
        ([], [fact()], Verdict.accepted, "can only be corrected"),
        ([fact(), fact()], [], Verdict.accepted, None),
        ([], [fact()], Verdict.corrected, None),
    ],
)
def test_a_check_is_refused_with_why(facts, rejected, verdict, reason):
    found = refusal(facts, rejected, verdict, RULES)
    assert found is None if reason is None else reason in found


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


def test_a_paragraph_offers_each_whole_number_where_it_is_written():
    paragraph = (
        "Le chiffre d'affaires atteint 36 681 MDH en 2025, contre 36 699 MDH en 2024 ; "
        "le dividende proposé est de 4,00 dirhams, soit 36 681 au total."
    )
    numbers = numbers_in(paragraph)
    assert [n.text for n in numbers] == ["36 681", "2025", "36 699", "2024", "4,00", "36 681"]
    assert all(paragraph[n.start :].startswith(n.text) for n in numbers)


def test_numbers_side_by_side_in_a_flat_row_are_two():
    numbers = numbers_in("Chiffre d'affaires 36 699 36 681 -988")
    assert [n.text for n in numbers] == ["36 699", "36 681", "-988"]


def test_a_number_written_twice_has_the_words_around_each_place():
    paragraph = (
        "Le chiffre d'affaires atteint 36 681 MDH en 2025, contre 36 699 MDH en 2024 ; "
        "le dividende proposé est de 4,00 dirhams, soit 36 681 au total."
    )
    first, *_, last = numbers_in(paragraph)
    assert around(paragraph, first) == (
        "Le chiffre d'affaires atteint 36 681 MDH en 2025, contre 36 699 MDH…"
    )
    assert around(paragraph, last) == "…est de 4,00 dirhams, soit 36 681 au total."


def test_the_words_around_a_number_are_cut_at_whole_words_or_kept_whole():
    unbroken = "x" * 40
    paragraph = f"{unbroken}:36 681:{unbroken}"
    [number] = numbers_in(paragraph)
    assert around(paragraph, number) == f"…{'x' * 31}:36 681:{'x' * 31}…"
    paragraph = "Le chiffre d'affaires consolidé atteint 36 681 MDH sur l'exercice clos en 2025"
    first = numbers_in(paragraph)[0]
    assert around(paragraph, first) == (
        "…d'affaires consolidé atteint 36 681 MDH sur l'exercice clos en 2025"
    )
    short = "Total 36 681 MDH"
    [number] = numbers_in(short)
    assert around(short, number) == short


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
        config.kpi_rules(empty)


def test_one_filing_s_check_is_the_value_s_check_across_filings():
    """#24 D4: a value is checked once every figure of one filing stating it is."""
    other = DOCUMENT.model_copy(update={"id": "d2"})
    checked = review(day=10)
    figures = [
        figure("36 681", "36681000000", review=checked),
        figure("36 681", "36681000000", document=other),
    ]
    assert value_check(figures) == checked
    partly = [*figures, figure("36 681", "36681000000", page=9)]
    assert value_check(partly) is None


def test_another_filing_s_check_covers_a_value_it_states_within_precision():
    checked = [("d1", figure("36 681", "36681000000"), "check")]
    assert covering(figure("36,7", "36700000000", scale=BILLIONS), "d2", checked) == "check"
    assert covering(figure("36 699", "36699000000"), "d2", checked) is None
    # Never its own filing's.
    assert covering(figure("36 681", "36681000000"), "d1", checked) is None
