"""How a table reads for search: one line per row, each value after its column name. Pure.

The chunker sizes a table by these lines, and the index text is made of them, so a table part
that fits the cap is the text that gets embedded.
"""

from collections.abc import Sequence


def corner(header: str) -> str:
    """The top-left cell: it names the label column or gives the unit, "(En millions de MAD)"."""
    return cells(header)[0]


def row_lines(header: str, rows: Sequence[str]) -> list[str]:
    """One line per row, "Chiffre d'affaires: 2025 36 802 · 2024 36 699"; "" for an empty row."""
    _, *columns = cells(header)
    lines = []
    for row in rows:
        label, *values = cells(row)
        pairs = [
            f"{column} {value}" if column else value
            for column, value in zip(columns, values)
            if value
        ]
        line = " · ".join(pairs)
        if label:
            line = f"{label}: {line}" if line else label
        lines.append(line)
    return lines


def cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]
