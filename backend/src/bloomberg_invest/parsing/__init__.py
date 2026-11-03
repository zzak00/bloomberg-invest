"""The parser interface. Implementations live in their own modules so the API never imports them."""

from pathlib import Path
from typing import Protocol

from bloomberg_invest.domain import ParsedDocument


class Parser(Protocol):
    tool: str
    tool_version: str
    config: dict[str, str]

    def parse(self, pdf: Path, output: Path) -> ParsedDocument:
        """Parse the PDF and save the tool's own full output to `output`."""
