"""The label map: the line items a financial figure may point to (#19 R6, R14). Loaded from the
versioned configuration in `bloomberg_invest/config/line_items/`."""

from dataclasses import dataclass
from typing import Literal

Kind = Literal["flow", "stock"]


@dataclass(frozen=True)
class LineItem:
    name: str
    title: str
    definition: str  # what the LLM reads to pick it
    statement: str  # a key of `LabelMap.statements`
    kind: Kind


@dataclass(frozen=True)
class LabelMap:
    version: str
    sha256: str  # of the configuration file, so a Run names exactly what it used
    statements: dict[str, str]  # key -> title, in the order the dossier lists them
    items: dict[str, LineItem]

    def __post_init__(self) -> None:
        for item in self.items.values():
            if item.statement not in self.statements:
                raise ValueError(f"line item {item.name!r} names no known statement")
            if item.kind not in ("flow", "stock"):
                raise ValueError(f"line item {item.name!r} has kind {item.kind!r}")
