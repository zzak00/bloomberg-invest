"""Runtime configuration from the environment; Docker Compose sets these."""

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    data_dir: Path
    # Which parser implementation ingests filings; see `bootstrap.PARSERS`.
    parser: str = "docling"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            neo4j_uri=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
            neo4j_user=os.environ.get("NEO4J_USER", "neo4j"),
            neo4j_password=os.environ["NEO4J_PASSWORD"],
            data_dir=Path(os.environ.get("DATA_DIR", "data")),
            parser=os.environ.get("PARSER", "docling"),
        )
