"""KPI values (#27): formulas read from the rules, computed only from checked inputs, and why
not otherwise (#7, #19 R10, R12, R14)."""

from dataclasses import replace
from decimal import Decimal

import pytest

from bloomberg_invest import config
from bloomberg_invest.domain.kpis import (
    Formula,
    InputValue,
    Kpi,
    KpiResult,
    KpiRules,
    KpiStatus,
    compute,
)

LABEL_MAP = config.label_map()
RULES = config.kpi_rules(LABEL_MAP)

# Maroc Telecom, consolidated IFRS, MAD (golden figures.csv): FY2025, FY2024 and what FY2025's
# averages and the F-score's year-on-year tests need of FY2023.
MAROC_TELECOM = {
    2025: {
        "revenue": "36681000000",
        "ebitda": "18493000000",
        "operating_income_ebit": "13547000000",
        "pre_tax_income": "12533000000",
        "tax_expense": "-4610000000",
        "net_income": "7923000000",
        "net_income_group_share": "6968000000",
        "interest_expense": "-1053000000",
        "total_assets": "75811000000",
        "current_assets": "15168000000",
        "current_liabilities": "39054000000",
        "cash_and_equivalents": "1966000000",
        "long_term_debt": "10449000000",
        "short_term_debt": "9154000000",
        "equity": "24785000000",
        "equity_group_share": "20478000000",
        "shares_outstanding": "879095340",
        "operating_cash_flow": "18499000000",
        "capex_cash": "-9404000000",
        "declared_dividend_per_share": "4.00",
    },
    2024: {
        "revenue": "36699000000",
        "net_income": "2660000000",
        "net_income_group_share": "1801000000",
        "total_assets": "70374000000",
        "current_assets": "15089000000",
        "current_liabilities": "45266000000",
        "cash_and_equivalents": "1979000000",
        "long_term_debt": "5630000000",
        "short_term_debt": "18812000000",
        "equity": "18702000000",
        "equity_group_share": "14908000000",
        "shares_outstanding": "879095340",
        "operating_cash_flow": "11598000000",
    },
    2023: {"total_assets": "65543000000"},
}


def inputs(data=MAROC_TELECOM, checked: bool = True) -> dict[tuple[str, int], InputValue]:
    return {
        (name, year): InputValue((Decimal(value),), checked, (f"{name}-{year}",))
        for year, values in data.items()
        for name, value in values.items()
    }


def results(given=None, year: int = 2025, financial: bool = False):
    return {r.kpi: r for r in compute(RULES, given or inputs(), year, financial)}


def as_shown(value: Decimal, places: int = 1) -> Decimal:
    return value.quantize(Decimal(1).scaleb(-places))


@pytest.mark.parametrize(
    ("kpi", "expected", "places"),
    [
        # Hand-computed from the golden figures; a ratio is a fraction, shown x 100.
        ("revenue_growth", "-0.0005", 4),  # 36 681 / 36 699 - 1
        ("net_income_growth", "1.979", 3),  # 7 923 / 2 660 - 1
        ("ebitda_margin", "0.504", 3),  # 18 493 / 36 681: AC6's 50,4 %
        ("operating_margin", "0.369", 3),  # 13 547 / 36 681
        ("net_margin", "0.216", 3),  # 7 923 / 36 681
        ("roe", "0.394", 3),  # 6 968 / ((20 478 + 14 908) / 2)
        ("roa", "0.108", 3),  # 7 923 / ((75 811 + 70 374) / 2)
        # 13 547 x (1 - 4 610 / 12 533) / avg(24 785 + 19 603 - 1 966, 18 702 + 24 442 - 1 979)
        ("roic", "0.205", 3),
        ("cash_conversion", "2.33", 2),  # 18 499 / 7 923
        ("free_cash_flow", "9095000000", 0),  # 18 499 - 9 404
        ("fcf_margin", "0.248", 3),  # 9 095 / 36 681
        ("debt_to_equity", "0.79", 2),  # (10 449 + 9 154) / 24 785
        ("net_debt_to_ebitda", "0.95", 2),  # (19 603 - 1 966) / 18 493: shown 1,0x
        ("interest_coverage", "12.9", 1),  # 13 547 / 1 053
        ("current_ratio", "0.39", 2),  # 15 168 / 39 054
        ("payout_ratio", "0.505", 3),  # 4,00 x 879 095 340 / 6 968 m
    ],
)
def test_each_kpi_computes_its_formula_from_checked_inputs(kpi, expected, places):
    result = results()[kpi]
    assert result.status == KpiStatus.computed, result.reason
    assert as_shown(result.value, places) == Decimal(expected)


def test_a_value_records_every_input_it_read_and_the_facts_behind_them():
    roe = results()["roe"]
    assert [(u.name, u.fiscal_year) for u in roe.used] == [
        ("net_income_group_share", 2025),
        ("equity_group_share", 2025),
        ("equity_group_share", 2024),
    ]
    assert roe.sources == (
        "equity_group_share-2024",
        "equity_group_share-2025",
        "net_income_group_share-2025",
    )


def test_gross_margin_is_not_meaningful_with_no_gross_profit():
    gross = results()["gross_margin"]
    assert gross.status == KpiStatus.not_meaningful
    assert gross.value is None
    assert gross.reason == ("Not meaningful: the income statement is by nature: no gross profit")


def test_an_unchecked_input_leaves_no_value_and_names_it():
    given = inputs()
    given[("ebitda", 2025)] = replace(given[("ebitda", 2025)], checked=False)
    margin = results(given)["ebitda_margin"]
    assert margin.status == KpiStatus.unchecked
    assert margin.value is None
    assert margin.reason == "Waiting for check: EBITDA FY2025"
    # Only the KPIs reading it wait.
    assert results(given)["net_margin"].status == KpiStatus.computed


def test_every_problem_is_named_worst_first():
    given = inputs()
    del given[("equity_group_share", 2024)]
    given[("net_income_group_share", 2025)] = InputValue(
        (Decimal(6968000000), Decimal(6969000000)), False, ("a", "b")
    )
    given[("equity_group_share", 2025)] = replace(
        given[("equity_group_share", 2025)], checked=False
    )
    roe = results(given)["roe"]
    assert roe.status == KpiStatus.missing
    assert roe.reason == (
        "Missing: Equity, group share FY2024; "
        "Two values for: Net income, group share FY2025; "
        "Waiting for check: Equity, group share FY2025"
    )


def test_banks_and_insurers_read_not_meaningful_where_7_says_so():
    found = results(financial=True)
    assert found["net_margin"].status == KpiStatus.not_meaningful
    assert found["net_margin"].reason == "Not meaningful for banks and insurers"
    assert found["f_score"].status == KpiStatus.not_meaningful
    # ROE, ROA and payout apply to every company.
    for kpi in ("roe", "roa", "payout_ratio"):
        assert found[kpi].status == KpiStatus.computed


def test_a_kpi_whose_condition_fails_is_not_meaningful():
    given = inputs({**MAROC_TELECOM, 2024: {**MAROC_TELECOM[2024], "net_income": "-5"}})
    growth = results(given)["net_income_growth"]
    assert growth.status == KpiStatus.not_meaningful
    assert growth.reason == "Not meaningful unless net income FY-1 > 0"


def test_a_zero_divisor_is_not_meaningful():
    given = inputs({**MAROC_TELECOM, 2025: {**MAROC_TELECOM[2025], "current_liabilities": "0"}})
    ratio = results(given)["current_ratio"]
    assert ratio.status == KpiStatus.not_meaningful
    assert ratio.reason == "Not meaningful: current liabilities is zero"


def test_the_f_score_counts_the_tests_that_apply_out_of_8_with_no_gross_profit():
    score = results()["f_score"]
    tests = {t.name: t for t in score.tests}
    assert len(tests) == 9
    assert score.status == KpiStatus.computed, score.reason
    assert (score.value, score.out_of) == (6, 8)
    # FY2025 against FY2024, from the golden figures.
    assert tests["roa_positive"].passed is True
    assert tests["cfo_positive"].passed is True
    assert tests["roa_up"].passed is True  # 7 923 / 70 374 > 2 660 / 65 543
    assert tests["accruals"].passed is True  # 18 499 > 7 923
    assert tests["leverage_down"].passed is False  # 10 449 / 75 811 > 5 630 / 70 374
    assert tests["current_ratio_up"].passed is True  # 0,39 > 0,33
    assert tests["no_new_shares"].passed is True
    assert tests["asset_turnover_up"].passed is False  # 36 681 / 70 374 < 36 699 / 65 543
    assert tests["gross_margin_up"].status == KpiStatus.not_meaningful


def test_the_f_score_waits_until_every_test_that_applies_has_checked_inputs():
    given = inputs()
    del given[("total_assets", 2023)]
    score = results(given)["f_score"]
    tests = {t.name: t for t in score.tests}
    assert score.status == KpiStatus.missing
    assert score.value is None
    assert score.reason == "No score until all 8 tests have checked inputs: 2 wait"
    assert tests["roa_up"].reason == "Missing: Total assets FY2023"
    assert tests["roa_positive"].passed is True


# A company passing all nine tests, gross profit reported.
STRONG = {
    2025: {
        "net_income": "10",
        "total_assets": "100",
        "operating_cash_flow": "20",
        "long_term_debt": "10",
        "current_assets": "30",
        "current_liabilities": "20",
        "shares_outstanding": "5",
        "revenue": "200",
        "gross_profit": "80",
    },
    2024: {
        "net_income": "5",
        "total_assets": "100",
        "operating_cash_flow": "8",
        "long_term_debt": "20",
        "current_assets": "20",
        "current_liabilities": "20",
        "shares_outstanding": "5",
        "revenue": "150",
        "gross_profit": "50",
    },
    2023: {"total_assets": "100"},
}


def score_of(data) -> KpiResult:
    rules = replace(RULES, not_reported={})  # as if gross profit were reported
    return {r.kpi: r for r in compute(rules, inputs(data), 2025, False)}["f_score"]


def test_the_f_score_counts_the_tests_passed_once_all_are_computed():
    score = score_of(STRONG)
    assert score.status == KpiStatus.computed
    assert (score.value, score.out_of) == (9, 9)
    assert all(t.passed for t in score.tests)


@pytest.mark.parametrize(
    ("change", "failed"),
    [
        # A loss, smaller than the year before: ROA is negative but up.
        ({2025: {"net_income": "-10"}, 2024: {"net_income": "-20"}}, {"roa_positive"}),
        # No operating cash flow is also below net income.
        ({2025: {"operating_cash_flow": "0"}}, {"cfo_positive", "accruals"}),
        ({2024: {"net_income": "20"}}, {"roa_up"}),
        ({2025: {"operating_cash_flow": "5"}}, {"accruals"}),
        ({2025: {"long_term_debt": "30"}}, {"leverage_down"}),
        ({2025: {"current_assets": "15"}}, {"current_ratio_up"}),
        ({2025: {"shares_outstanding": "6"}}, {"no_new_shares"}),
        ({2025: {"gross_profit": "50"}}, {"gross_margin_up"}),
        ({2025: {"revenue": "100", "gross_profit": "40"}}, {"asset_turnover_up"}),
    ],
)
def test_each_f_score_test_fails_on_its_formula(change, failed):
    data = {year: {**values, **change.get(year, {})} for year, values in STRONG.items()}
    score = score_of(data)
    assert {t.name for t in score.tests if t.passed is False} == failed
    assert score.value == 9 - len(failed)


@pytest.mark.parametrize(
    "text",
    [
        "__import__('os').system('true')",
        "revenue ** 2",
        "revenue if ebitda else 0",
        "revenue.real",
        "prev(revenue, 2)",
        "max(revenue, ebitda)",
        "revenue < ebitda < 3",
        "'text'",
        "prev",
    ],
)
def test_a_formula_may_use_only_arithmetic_comparisons_and_prev_avg_abs(text):
    with pytest.raises(ValueError, match="formula"):
        Formula.parse(text)


def test_a_formula_reads_as_words_on_the_kpis_page():
    roic = next(k for k in RULES.kpis if k.name == "roic")
    assert roic.formula.render(RULES.titles) == (
        "operating income × (1 - income tax / income before tax) / average (total equity "
        "+ long-term debt + short-term debt - cash and cash equivalents)"
    )
    assert Formula.parse("a - (b - c) / (d * e)").render({}) == "a - (b - c) / (d × e)"
    assert Formula.parse("(a - b) / prev(c)").render({}) == "(a - b) / c FY-1"


def test_a_computed_kpi_s_inputs_are_read_from_its_formula():
    payout = next(k for k in RULES.kpis if k.name == "payout_ratio")
    assert [i.line_item for i in payout.inputs] == ["shares_outstanding", "net_income_group_share"]
    assert RULES.declared_feeds("per_share") == ["Payout ratio"]
    # Dividends paid in a year are the previous year's dividend: they feed no KPI (#53).
    assert RULES.feeds("dividends_paid", "") == []


def test_a_formula_naming_an_unknown_line_item_fails():
    kpi = Kpi("x", "X", (), formula=Formula.parse("goodwill / revenue"))
    rules = KpiRules("v9", "0" * 64, (kpi,))
    with pytest.raises(ValueError, match="'goodwill', which label map v1 does not have"):
        rules.check_against(LABEL_MAP)


def test_every_quality_kpi_of_7_and_ebitda_margin_is_computed_with_its_page_texts():
    computed = [k for k in RULES.kpis if k.computed]
    assert len(computed) == 18  # 16 of #7, EBITDA margin, and the F-score
    for kpi in computed:
        assert kpi.theme and kpi.means and kpi.read, kpi.name


def test_a_kpi_s_theme_needs_a_title():
    kpi = Kpi("x", "X", (), theme="mystery", formula=Formula.parse("revenue"))
    rules = KpiRules("v9", "0" * 64, (kpi,), themes={"growth": "Growth"})
    with pytest.raises(ValueError, match="theme 'mystery', which has no title"):
        rules.check_against(LABEL_MAP)
