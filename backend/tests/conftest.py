import os
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from neo4j import Driver, GraphDatabase

from bloomberg_invest.domain import (
    DocType,
    DocumentMeta,
    Organisation,
    PageInfo,
    ParsedDocument,
    RunInfo,
    SectionNode,
)
from bloomberg_invest.store.neo4j_store import Neo4jStore

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def driver() -> Iterator[Driver]:
    # A throwaway database: `docker compose --profile test up -d --wait neo4j-test` locally,
    # a service container in CI. Every test wipes it.
    uri = os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688")
    password = os.environ.get("NEO4J_TEST_PASSWORD", "test-password")
    with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
        driver.verify_connectivity()
        yield driver


@pytest.fixture
def store(driver: Driver) -> Neo4jStore:
    driver.execute_query("MATCH (n) DETACH DELETE n")
    store = Neo4jStore(driver)
    store.ensure_schema()
    return store


@pytest.fixture
def meta() -> DocumentMeta:
    return DocumentMeta(
        issuer=Organisation(isin="MA0000011488", name="Maroc Telecom"),
        doc_type=DocType.annual_report,
        fiscal_year=2025,
        source_url="https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf",
    )


@pytest.fixture
def parsed() -> ParsedDocument:
    return ParsedDocument(
        pages=[PageInfo(number=n, width=595.0, height=842.0) for n in (1, 2, 3)],
        sections=[
            SectionNode(
                title="1. RÉSULTATS",
                level=1,
                page=1,
                bbox=(50, 60, 300, 80),
                children=[
                    SectionNode(title="1.1 En dirham", level=2, page=2, bbox=(50, 90, 250, 104)),
                    SectionNode(title="1.2 En euro", level=2, page=3, bbox=None),
                ],
            ),
            SectionNode(title="2. VUE D'ENSEMBLE", level=1, page=3, bbox=(50, 400, 300, 420)),
        ],
    )


def make_run(minute: int = 0) -> RunInfo:
    return RunInfo(
        step="parse",
        tool="docling",
        tool_version="2.145.0",
        config={"table_structure": "TableFormer v1"},
        started_at=datetime(2026, 11, 3, 9, minute, tzinfo=UTC),
        finished_at=datetime(2026, 11, 3, 9, minute + 4, tzinfo=UTC),
        output="parses/90e8b73c/20261103T090000Z-docling.json",
    )
