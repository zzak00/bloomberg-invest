"""When two statements of a figure agree (#19 R8, its first part)."""

from dataclasses import dataclass
from decimal import Decimal

from bloomberg_invest.domain.dossier import agreeing, precision

MILLIONS, BILLIONS = 1_000_000, 1_000_000_000


@dataclass(frozen=True)
class Stated:
    value: str
    value_as_written: str
    scale: int


def test_precision_is_the_step_the_value_is_written_to_in_the_base_unit():
    assert precision("36 681", MILLIONS) == Decimal(1_000_000)
    assert precision("36,7", BILLIONS) == Decimal(100_000_000)
    assert precision("4,01", 1) == Decimal("0.01")
    assert precision("36.7", BILLIONS) == Decimal(100_000_000)  # a dot decimal counts too
    assert precision("36.681", MILLIONS) == Decimal(1_000_000)  # dot-thousands are no decimals


def test_a_rounded_statement_agrees_with_the_exact_one():
    exact = Stated("36681000000", "36 681", MILLIONS)
    rounded = Stated("36700000000", "36,7", BILLIONS)

    assert agreeing([rounded, exact]) == [[exact, rounded]]


def test_values_one_step_apart_at_the_same_precision_disagree():
    first = Stated("6969000000", "6 969", MILLIONS)
    second = Stated("6968000000", "6 968", MILLIONS)

    assert agreeing([first, second]) == [[first], [second]]


def test_a_rounded_value_that_is_not_the_exact_one_rounded_disagrees():
    exact = Stated("36681000000", "36 681", MILLIONS)
    off = Stated("36800000000", "36,8", BILLIONS)

    assert agreeing([exact, off]) == [[exact], [off]]
