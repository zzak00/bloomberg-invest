"""The parser-neutral output every adapter writes, so one scorer can compare them."""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Cell:
    row: int
    col: int
    text: str
    kind: str  # "column_header", "row_header" or "content"
    col_span: int = 1


@dataclass
class Table:
    pages: list[int]
    caption: str
    cells: list[Cell]


@dataclass
class Paragraph:
    page: int
    text: str


@dataclass
class ParseResult:
    parser: str
    version: str
    seconds: float
    page_count: int
    tables: list[Table] = field(default_factory=list)
    paragraphs: list[Paragraph] = field(default_factory=list)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1))

    @classmethod
    def load(cls, path: Path) -> "ParseResult":
        raw = json.loads(path.read_text())
        tables = [
            Table(t["pages"], t["caption"], [Cell(**c) for c in t["cells"]])
            for t in raw.pop("tables")
        ]
        paragraphs = [Paragraph(**p) for p in raw.pop("paragraphs")]
        return cls(**raw, tables=tables, paragraphs=paragraphs)
