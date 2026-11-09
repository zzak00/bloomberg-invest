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
