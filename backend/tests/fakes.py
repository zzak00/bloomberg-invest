"""Fakes for service tests: plain classes that pass the same contracts as the real adapters."""

import html
import json
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bloomberg_invest import config
from bloomberg_invest.adapters.prices import PriceSource, PriceSourceError
from bloomberg_invest.domain.prices import Close, Holiday, ListedShare
from bloomberg_invest.service_layer.extract import Extraction
from bloomberg_invest.service_layer.facts import FactExtraction


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


class FakePriceSource(PriceSource):
    """An exchange that behaves as the Bourse de Casablanca does (#15): a row per share each
    session, and nothing for a range that starts before its history. A share in `failing`
    cannot be read, as when the source breaks halfway through a run."""

    mic = "XCAS"
    source = "bourse-casablanca"
    currency = "MAD"

    def __init__(self, shares, sessions, history_start, holidays=(), failing=()) -> None:
        self.shares = list(shares)
        self.sessions = sessions  # ticker -> {date: Decimal | None}
        self.history_start = history_start
        self.holiday_list = list(holidays)
        self.failing = set(failing)
        self.asked: list[tuple[str, date, date]] = []

    def listings(self) -> list[ListedShare]:
        return self.shares

    def holidays(self) -> list[Holiday]:
        return self.holiday_list

    def closes(self, ticker: str, start: date, end: date) -> list[Close]:
        self.asked.append((ticker, start, end))
        if ticker in self.failing:
            raise PriceSourceError("the source timed out")
        if start < self.history_start:
            return []
        rows = self.sessions.get(ticker, {})
        return [Close(d, rows[d]) for d in sorted(rows) if start <= d <= end]


BOURSE_FIXTURES = Path(__file__).parent / "fixtures" / "bourse"
# Where the Bourse's rolling three years start, in the made-up exchange.
BOURSE_HISTORY = date(2023, 11, 13)


def bourse_server(url: str) -> bytes:
    """The Bourse's site as far as the fixtures go, behaving as its server does (#15): it
    filters a range by date, and answers nothing for a range starting before its history."""
    if url.endswith("/emetteurs/liste-emetteurs"):
        return (BOURSE_FIXTURES / "issuers.html").read_bytes()
    if url.endswith("/market-data/jours-feries"):
        return (BOURSE_FIXTURES / "holidays.html").read_bytes()
    query = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
    start, end = date.fromisoformat(query["startDate"]), date.fromisoformat(query["endDate"])
    answer = json.loads((BOURSE_FIXTURES / "closes.json").read_bytes())
    if query["instrument"] != "ABC" or start < BOURSE_HISTORY:
        return (BOURSE_FIXTURES / "empty.json").read_bytes()
    items = [
        i
        for i in answer["items"]
        if start <= datetime.strptime(i["seance"], "%d/%m/%Y").date() <= end
    ]
    return json.dumps({"totalCount": len(items), "items": items}).encode()


class FactReadingLLM:
    """Answers fact prompts the way the real model does, from the page it is shown: each fact in
    `facts`, by kind, comes back citing the paragraph of the page holding its quote."""

    tool = "fake-llm"
    tool_version = "1.0"
    model = "fake-model"

    def __init__(self, facts: dict[str, list[dict]] | None = None) -> None:
        self.config = {"deployment": "fake-model"}
        self.facts = facts or {}
        self.pages: list[str] = []

    def complete_json(self, system: str, user: str, schema_name: str, schema: dict) -> dict:
        self.pages.append(next(line for line in user.splitlines() if line.startswith("Page ")))
        paragraphs = re.findall(r"^\[(p[\d.]+)\] (.*)$", user, re.MULTILINE)
        answer: dict[str, list[dict]] = {name: [] for name in schema["properties"]}
        for kind, items in self.facts.items():
            for item in items:
                for source_id, text in paragraphs:
                    if item["quote"] in text:
                        answer[kind].append(item | {"source_id": source_id})
        return answer


def fake_fact_extraction(facts: dict[str, list[dict]] | None = None) -> FactExtraction:
    """Fact extraction by `FactReadingLLM`, with the real prompt."""
    return FactExtraction(FactReadingLLM(facts), config.facts_prompt())
