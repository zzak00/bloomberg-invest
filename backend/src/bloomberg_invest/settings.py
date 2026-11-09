"""Runtime configuration from the environment; Docker Compose sets these."""

import os
from dataclasses import dataclass
from pathlib import Path

from bloomberg_invest.domain.chunking import Caps


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    data_dir: Path
    # Which parser implementation ingests filings; see `bootstrap.PARSERS`.
    parser: str = "docling"
    # Token caps (#19 R2): a section's text Chunk, and a table read one line per row (cl100k).
    chunk_cap: int = 2000
    table_cap: int = 1500
    # Which model embeds Chunks and queries; see `bootstrap.EMBEDDERS`.
    embedder: str = "qwen3-0.6b"
    # Which LLM extracts figures; see `bootstrap.LLMS`. Its secrets are checked only when an
    # LLM is built, so the API, which never extracts, runs without them.
    llm: str = "azure-openai"
    azure_openai_endpoint: str | None = None
    azure_openai_api_key: str | None = None
    extract_deployment: str = "gpt-5.6-sol"
    # Pages sent to the LLM at once.
    extract_concurrency: int = 4
    # Record the LLM's answers to this file, or replay them from it instead of calling out.
    llm_record: Path | None = None
    llm_replay: Path | None = None

    @property
    def caps(self) -> Caps:
        return Caps(text=self.chunk_cap, table=self.table_cap)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ["NEO4J_PASSWORD"],
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            parser=os.environ.get("PARSER", "docling"),
            chunk_cap=int(os.environ.get("CHUNK_CAP", "2000")),
            table_cap=int(os.environ.get("TABLE_CAP", "1500")),
            embedder=os.environ.get("EMBEDDER", "qwen3-0.6b"),
            llm=os.environ.get("LLM", "azure-openai"),
            azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT") or None,
            azure_openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY") or None,
            extract_deployment=os.environ.get("EXTRACT_DEPLOYMENT", "gpt-5.6-sol"),
            extract_concurrency=int(os.environ.get("EXTRACT_CONCURRENCY", "4")),
            llm_record=_path(os.environ.get("LLM_RECORD")),
            llm_replay=_path(os.environ.get("LLM_REPLAY")),
        )


def _path(value: str | None) -> Path | None:
    return Path(value) if value else None
