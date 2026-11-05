"""Fakes for service tests: plain classes that pass the same contracts as the real adapters."""

from pathlib import Path


class WordCounter:
    """Counts words, so tests can reason about chunk sizes without a tokenizer."""

    name = "words"

    def __call__(self, text: str) -> int:
        return len(text.split())


class BrokenParser:
    """A parser that crashes, optionally after saving its output."""

    def __init__(self, saves_output: bool = False) -> None:
        self.tool = "docling"
        self.tool_version = "2.145.0"
        self.config = {"table_structure": "TableFormer v1"}
        self.saves_output = saves_output

    def parse(self, pdf: Path, output: Path):
        if self.saves_output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{}")
        raise RuntimeError("the layout model crashed")

    def read_blocks(self, output: Path):
        raise RuntimeError("the saved output is unreadable")
