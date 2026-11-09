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
        )
