"""Parsing figures and checking them against their source (#19 R6, #10)."""

from datetime import date
from decimal import Decimal

import pytest

from bloomberg_invest.domain.figures import (
    Unit,
    matches_cell,
    matches_span,
    number,
    parse_unit,
    parse_value,
    period,
    scaled,
)


@pytest.mark.parametrize(
    ("written", "value"),
    [
        ("36 681", Decimal(36681)),
        ("36 681", Decimal(36681)),
        ("-1 015", Decimal(-1015)),
        ("−7 711", Decimal(-7711)),
        ("(988)", Decimal(-988)),
        ("1 284,6", Decimal("1284.6")),
        ("12,5 %", Decimal("12.5")),
        ("4,01", Decimal("4.01")),
        ("36.681", Decimal(36681)),
        ("4.01", Decimal("4.01")),
        ("1.284,6", Decimal("1284.6")),
        ("879 095 340", Decimal(879095340)),
    ],
)
def test_values_are_read_in_french_notation(written, value):
    assert parse_value(written) == value


@pytest.mark.parametrize("written", ["", "n.s.", "-", "36 681 / 36 699", "12a"])
def test_anything_but_one_number_is_not_a_value(written):
    assert parse_value(written) is None


@pytest.mark.parametrize(
    ("written", "unit"),
    [
        ("MAD millions", Unit("MAD", 1_000_000, "MAD")),
        ("MAD thousands", Unit("MAD", 1_000, "MAD")),
        ("MAD milliards", Unit("MAD", 1_000_000_000, "MAD")),
        ("En millions de dirhams", Unit("MAD", 1_000_000, "MAD")),
        ("MDH", Unit("MAD", 1_000_000, "MAD")),
        ("KDH", Unit("MAD", 1_000, "MAD")),
        ("MAD", Unit("MAD", 1, "MAD")),
        ("EUR millions", Unit("EUR", 1_000_000, "EUR")),
        ("%", Unit("%")),
        ("shares", Unit("shares")),
        ("actions", Unit("shares")),
        ("MAD per share", Unit("MAD/share", 1, "MAD")),
        ("DH par action", Unit("MAD/share", 1, "MAD")),
    ],
)
def test_units_name_a_currency_and_scale(written, unit):
    assert parse_unit(written) == unit


@pytest.mark.parametrize("written", ["", "units", "millions", "MAD millions per share"])
def test_a_unit_without_a_currency_or_with_a_scaled_share_is_unknown(written):
    assert parse_unit(written) is None


def test_scaled_values_are_exact_decimal_strings():
    millions = Unit("MAD", 1_000_000, "MAD")
    assert scaled(Decimal(36681), millions) == "36681000000"
    assert scaled(Decimal("1284.6"), millions) == "1284600000"
    assert scaled(Decimal(-988), millions) == "-988000000"
    assert scaled(Decimal("4.01"), Unit("MAD/share", 1, "MAD")) == "4.01"
    assert scaled(Decimal("12.50"), Unit("%")) == "12.5"


def test_the_cell_check_compares_numbers_not_spacing_or_sign_notation():
    assert number("(988)") == number("-988") == "-988"
    assert matches_cell("36 681", "36 681")
    assert matches_cell("-988", "(988)")
    assert not matches_cell("36 681", "36 699")
    assert not matches_cell("36 681", "-36 681")
    assert not matches_cell("", "")


def test_the_span_check_finds_the_value_as_written_in_the_paragraph():
    paragraph = "Le Conseil propose un dividende de 4,01 dirhams par action."
    assert matches_span("4,01", paragraph)
    assert not matches_span("4,10", paragraph)
    assert not matches_span(" ", paragraph)


def test_a_flow_covers_its_fiscal_year_and_a_stock_holds_on_its_last_day():
    flow = period(2025, "flow")
    assert (flow.start, flow.end, flow.as_of) == (date(2025, 1, 1), date(2025, 12, 31), None)
    stock = period(2024, "stock")
    assert (stock.start, stock.end, stock.as_of) == (None, None, date(2024, 12, 31))
