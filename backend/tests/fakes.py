"""Fakes for service tests: plain classes that pass the same contracts as the real adapters."""

import html
import re
from pathlib import Path

from bloomberg_invest import config
from bloomberg_invest.service_layer.extract import Extraction


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


class FakeEmbedder:
    """Unit vectors from the words of a text: texts sharing words point the same way."""

    name = "fake-embedder"
    tool = "fake"
    tool_version = "1.0"
    max_tokens = 512
    dims = 16

    def __init__(self, broken: bool = False) -> None:
        self.broken = broken
        self.calls = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self.calls += 1
        if self.broken:
            raise RuntimeError("the model ran out of memory")
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    def _vector(self, text: str) -> list[float]:
        v = [0.0] * self.dims
        for word in text.lower().split():
            v[sum(map(ord, word)) % self.dims] += 1.0
        norm = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / norm for x in v]


class PageReadingLLM:
    """Answers extraction prompts the way the real model does, from the page it is shown.

    `figures` maps a value as written to the fields the model would return for it; each value
    found in a table cell or a paragraph of the page comes back citing that cell or paragraph.
    """

    tool = "fake-llm"
    tool_version = "1.0"
    model = "fake-model"

    def __init__(self, figures: dict[str, dict], broken: bool = False) -> None:
        self.config = {"deployment": "fake-model"}
        self.figures = figures
        self.broken = broken
        self.pages: list[str] = []

    def complete_json(self, system: str, user: str, schema_name: str, schema: dict) -> dict:
        if self.broken:
            raise RuntimeError("the deployment answered 429 Too Many Requests")
        self.pages.append(user.splitlines()[0])
        found = []
        for value, fields in self.figures.items():
            cell = rf'<td id="([^"]+)"[^>]*>{re.escape(html.escape(value))}</td>'
            paragraphs = re.findall(r"^\[(p[\d.]+)\] (.*)$", user, re.MULTILINE)
            cited = re.findall(cell, user) + [p for p, text in paragraphs if value in text]
            for source_id in cited:
                found.append(
                    {
                        "line_item": "revenue",
                        "fiscal_year": 2025,
                        "basis_scope": "consolidated",
                        "breakdown": "",
                        "unit_scale": "MAD millions",
                        **fields,
                        "source_id": source_id,
                        "value_as_written": fields.get("value_as_written", value),
                    }
                )
        return {"figures": found}


def fake_extraction(figures: dict[str, dict] | None = None) -> Extraction:
    """Extraction by `PageReadingLLM`, with the real label map and prompt."""
    return Extraction(PageReadingLLM(figures or {}), config.label_map(), config.extract_prompt())
