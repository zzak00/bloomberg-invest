"""When figures of one line item and year state the same value (#19 R8, its first part).

A filing states a figure several times, often rounded: `36,7` billions in the highlights and
`36 681` millions in the accounts. Those agree; `6 969` and `6 968` millions do not, and the
dossier shows both.
"""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

from bloomberg_invest.domain.figures import parse_value


class Stated(Protocol):
    @property
    def value(self) -> str: ...  # exact decimal in the base unit
    @property
    def value_as_written(self) -> str: ...
    @property
    def scale(self) -> int: ...


def precision(value_as_written: str, scale: int) -> Decimal:
    """The step a value is written to, in the base unit: 1 000 000 for `36 681` millions,
    100 000 000 for `36,7` billions, 0.01 for `4,01` dirhams."""
    parsed = parse_value(value_as_written)
    exponent = parsed.as_tuple().exponent if parsed is not None else 0
    return Decimal(scale).scaleb(exponent if isinstance(exponent, int) else 0)


def agreeing[S: Stated](stated: Sequence[S]) -> list[list[S]]:
    """The figures grouped by the value they state, finest first in each group. A figure joins
    a group when the group's finest value, rounded as the figure is written, is the figure's."""
    groups: list[list[S]] = []
    for figure in sorted(stated, key=lambda f: precision(f.value_as_written, f.scale)):
        half = precision(figure.value_as_written, figure.scale) / 2
        group = next(
            (g for g in groups if abs(Decimal(g[0].value) - Decimal(figure.value)) <= half), None
        )
        if group is None:
            groups.append([figure])
        else:
            group.append(figure)
    return groups
