import hashlib
import json
import os
import shutil
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from neo4j import Driver, GraphDatabase

from bloomberg_invest import config
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.store.neo4j_store import Neo4jStore
from bloomberg_invest.domain.extraction import SourceParagraph, drafts, page_sources
from bloomberg_invest.domain.model import (
    DocType,
    DocumentMeta,
    Organisation,
    PageInfo,
    ParsedDocument,
    ParsedTable,
    RunInfo,
    RunStep,
    SectionNode,
    TableCell,
)
from bloomberg_invest.settings import Settings

FIXTURES = Path(__file__).parent / "fixtures"
# The SHA-256 the store tests record their parse under.
SHA = "90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214"
# The golden report (Maroc Telecom RFA 2025), not committed: `golden` tests skip without it.
GOLDEN_PDF = Path(
    os.environ.get(
        "GOLDEN_PDF", Path(__file__).parents[2] / "data" / "inbox" / "Maroc_Telecom_RFA_2025.pdf"
    )
)
GOLDEN_SHA = SHA
GOLDEN = Path(__file__).parents[2] / "golden" / "maroc-telecom-rfa-2025"


def azure_settings() -> Settings:
    """Settings for the live Azure OpenAI model, from the environment; skips without secrets."""
    settings = Settings(
        neo4j_uri="",
        neo4j_user="",
        neo4j_password="",
        data_dir=Path("."),
        azure_openai_endpoint=os.environ.get("AZURE_OPENAI_ENDPOINT"),
        azure_openai_api_key=os.environ.get("AZURE_OPENAI_API_KEY"),
        extract_deployment=os.environ.get("EXTRACT_DEPLOYMENT", "gpt-5.6-sol"),
    )
    if not (settings.azure_openai_endpoint and settings.azure_openai_api_key):
        pytest.skip("needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY")
    pytest.importorskip("openai", reason="needs the ingest extra")
    return settings


@pytest.fixture(scope="session")
def driver() -> Iterator[Driver]:
    # A throwaway database: `docker compose --profile test up -d --wait neo4j-test` locally,
    # a service container in CI. Every test wipes it.
    uri = os.environ.get("NEO4J_TEST_URI", "bolt://localhost:7688")
    password = os.environ.get("NEO4J_TEST_PASSWORD", "test-password")
    with GraphDatabase.driver(uri, auth=("neo4j", password)) as driver:
        driver.verify_connectivity()
        yield driver


# The GraphStore contract: every store test runs on each implementation listed here.
@pytest.fixture(params=[Neo4jStore], ids=["neo4j"])
def store(request, driver: Driver) -> GraphStore:
    driver.execute_query("MATCH (n) DETACH DELETE n")
    store = request.param(driver)
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
        tables=[ParsedTable(page=2, bbox=(50, 120, 545, 200), cells=INCOME_CELLS)],
    )


def _cell(row: int, col: int, text: str) -> TableCell:
    top = 120 + 20 * row
    return TableCell(
        row=row,
        col=col,
        text=text,
        page=2,
        bbox=(50 + 165 * col, top, 210 + 165 * col, top + 16),
        column_header=row == 0,
    )


# An income statement extract: the table the store tests record on page 2.
INCOME_CELLS = [
    _cell(r, c, text)
    for r, row in enumerate(
        [
            ("(En millions MAD)", "31-déc.-24", "31-déc.-25"),
            ("Chiffre d'affaires", "36 699", "36 681"),
            ("Résultat net", "6 968", "7 112"),
        ]
    )
    for c, text in enumerate(row)
]


def make_run(minute: int = 0) -> RunInfo:
    return RunInfo(
        step=RunStep.parse,
        tool="docling",
        tool_version="2.145.0",
        config={"table_structure": "TableFormer v1"},
        started_at=datetime(2026, 11, 3, 9, minute, tzinfo=UTC),
        finished_at=datetime(2026, 11, 3, 9, minute + 4, tzinfo=UTC),
        output="parses/90e8b73c/20261103T090000Z-docling.json",
    )


@pytest.fixture
def document(store, meta, parsed):
    """A recorded parse: its Document id and its Section ids by title."""
    document_id = store.record_parse(meta, parsed, make_run(), SHA)
    detail = store.get_document(document_id)
    ids = {s.title: s.id for s in detail.sections}
    ids |= {c.title: c.id for s in detail.sections for c in s.children}
    return document_id, ids


# What the LLM answers for the income statement on page 2: (line item, year, cell id, value).
# Net income 2025 is misread (the cell says 7 112), so the check rejects it.
INCOME_ANSWER = [
    ("revenue", 2025, "t2.0.r1.c2", "36 681"),
    ("revenue", 2024, "t2.0.r1.c1", "36 699"),
    ("net_income", 2025, "t2.0.r2.c2", "7 121"),
]


def extract_income(
    store: GraphStore,
    document_id: str,
    answer=INCOME_ANSWER,
    minute: int = 10,
    page: int = 2,
    paragraphs: tuple[SourceParagraph, ...] = (),
) -> str:
    """Record an extract Run of one page, by default the income statement on page 2; return its
    Run id. An answer cites a cell, or a paragraph given (`p<page>.<n>`)."""
    sources = page_sources(page, paragraphs, store.cells(document_id))
    response = {
        "figures": [
            {
                "line_item": item,
                "fiscal_year": year,
                "basis_scope": "consolidated",
                "breakdown": "",
                "source_id": source,
                "value_as_written": value,
                "unit_scale": "MAD millions",
            }
            for item, year, source, value in answer
        ]
    }
    run = make_run(minute).model_copy(update={"step": RunStep.extract, "output": None})
    return store.record_extraction(document_id, drafts(response, sources, config.label_map()), run)


class CachedParser:
    """Docling, reusing its saved output for a PDF it already parsed with the same version and
    settings: the golden report takes minutes to parse. Our own reading of that output, into
    pages, tables and blocks, runs every time; a new Docling version or setting parses again."""

    def __init__(self, cache: Path) -> None:
        from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser

        self._parser = DoclingParser()
        self.tool, self.tool_version = self._parser.tool, self._parser.tool_version
        self.config = self._parser.config
        settings = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()
        self._cache = cache / f"{self.tool}-{self.tool_version}-{settings[:12]}"

    def parse(self, pdf: Path, output: Path):
        cached = self._cache / f"{hashlib.sha256(pdf.read_bytes()).hexdigest()}.json"
        if not cached.exists():
            parsed = self._parser.parse(pdf, output)
            cached.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(output, cached)
            return parsed
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(cached, output)
        return self._parser.read_parsed(output)

    def read_blocks(self, output: Path):
        return self._parser.read_blocks(output)


# Where the golden report's parses are kept between runs: next to it, never committed.
PARSE_CACHE = GOLDEN_PDF.parents[1] / "parses" / "test-cache"
