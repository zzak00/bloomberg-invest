"""Extracting figures from a parsed filing into Facts and RejectedFigures (#22 AC1-AC3).

The fixture PDF is parsed once by Docling; the LLM is a fake that answers from the page it is
shown, so the real page rendering, check and store run without a live model.
"""

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from conftest import FIXTURES
from fakes import PageReadingLLM

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest import config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser
from bloomberg_invest.domain.model import RunInfo, RunStep
from bloomberg_invest.service_layer.extract import ExtractFailed, Extraction, extract_document

SHA = hashlib.sha256((FIXTURES / "filing.pdf").read_bytes()).hexdigest()
OUTPUT = f"parses/{SHA}/20261109T090000Z-docling.json"
# What the fake model proposes, by the value it finds on the page.
FIGURES = {
    "36 681": {},
    "36 699": {"fiscal_year": 2024},
    "7 112": {"line_item": "net_income"},
    "4,01": {"line_item": "dividend_per_share", "unit_scale": "MAD per share"},
}


@pytest.fixture(scope="module")
def parser() -> DoclingParser:
    return DoclingParser()


@pytest.fixture(scope="module")
def parse(parser, tmp_path_factory):
    """The fixture parsed once: its ParsedDocument and the data dir holding Docling's output."""
    data = tmp_path_factory.mktemp("data")
    (data / OUTPUT).parent.mkdir(parents=True)
    return parser.parse(FIXTURES / "filing.pdf", data / OUTPUT), data


def parse_run(minute: int = 0) -> RunInfo:
    return RunInfo(
        step=RunStep.parse,
        tool="docling",
        tool_version="2.145.0",
        config={},
        started_at=datetime(2026, 11, 9, 9, minute, tzinfo=UTC),
        finished_at=datetime(2026, 11, 9, 9, minute + 1, tzinfo=UTC),
        output=OUTPUT,
    )


@pytest.fixture
def filing(store, meta, parse):
    parsed, data = parse
    return store.record_parse(meta, parsed, parse_run(), SHA), DocumentFiles(data)


def extract(store, filing, parser, llm):
    document_id, files = filing
    extraction = Extraction(llm, config.label_map(), config.extract_prompt(), concurrency=2)
    return extract_document(document_id, store, files, parser, extraction)


def test_each_figure_is_a_fact_with_its_period_basis_currency_and_cell(
    store, filing, parser, driver
):
    extracted = extract(store, filing, parser, PageReadingLLM(FIGURES))
    assert (extracted.figures, extracted.rejected) == (4, 0)

    figures = {(f.line_item, f.fiscal_year): f for f in store.figures("MA0000011488")}
    revenue = figures[("revenue", 2025)]
    assert (revenue.value, revenue.value_as_written) == ("36681000000", "36 681")
    assert (revenue.unit, revenue.scale, revenue.currency) == ("MAD", 1_000_000, "MAD")
    assert (revenue.line_item_title, revenue.statement) == ("Revenue", "income_statement")
    assert revenue.label == "Chiffre d'affaires"
    assert (revenue.period_start, revenue.period_end) == (date(2025, 1, 1), date(2025, 12, 31))
    assert revenue.as_of is None
    assert (revenue.basis_scope, revenue.basis_standard) == ("consolidated", "IFRS")
    assert revenue.recorded_at.tzinfo is not None
    assert (revenue.passage.kind, revenue.passage.page, revenue.passage.text) == (
        "cell",
        1,
        "36 681",
    )
    [box] = revenue.passage.boxes
    assert 0 < box.left < box.right < 595 and 0 < box.top < box.bottom < 842
    assert revenue.document.id == filing[0]

    records, _, _ = driver.execute_query(
        """
        MATCH (n:Fact {id: $id})-[:CITES]->(c:Cell:Passage)<-[:HAS_CELL]-(:Table)
        MATCH (n)-[:ABOUT]->(:Organisation {isin: 'MA0000011488'})
        MATCH (n)-[:PRODUCED_BY]->(r:Run {step: 'extract'})-[:PROCESSED]->(:Document {id: $doc})
        RETURN c.text AS cell
        """,
        id=revenue.id,
        doc=filing[0],
    )
    assert [r["cell"] for r in records] == ["36 681"]


def test_a_figure_quoted_from_a_paragraph_cites_the_span(store, filing, parser):
    extract(store, filing, parser, PageReadingLLM(FIGURES))

    dividend = next(f for f in store.figures("MA0000011488") if f.line_item == "dividend_per_share")
    assert (dividend.value, dividend.unit) == ("4.01", "MAD/share")
    assert dividend.passage.kind == "span"
    assert dividend.passage.quote == "4,01"
    assert dividend.passage.page == 2
    assert "dividende de 4,01 dirhams par action" in dividend.label
    assert dividend.passage.boxes and all(b.page == 2 for b in dividend.passage.boxes)


def test_a_figure_that_does_not_match_its_cell_is_rejected_and_never_a_fact(
    store, filing, parser, driver
):
    misread = FIGURES | {"36 681": {"value_as_written": "36 618"}}
    extracted = extract(store, filing, parser, PageReadingLLM(misread))

    assert extracted.rejected == 1
    shown = {f.value_as_written for f in store.figures("MA0000011488")}
    assert "36 618" not in shown and "36 681" not in shown
    records, _, _ = driver.execute_query(
        """
        MATCH (n:RejectedFigure)-[:CITES]->(c:Cell)
        RETURN n.value_as_written AS value, n.reason AS reason, c.text AS cell,
               n:Fact AS is_fact
        """
    )
    assert [dict(r) for r in records] == [
        {
            "value": "36 618",
            "reason": "its value differs from its cell",
            "cell": "36 681",
            "is_fact": False,
        }
    ]


def test_the_extract_run_records_the_model_prompt_and_label_map(store, filing, parser, driver):
    extracted = extract(store, filing, parser, PageReadingLLM(FIGURES))

    records, _, _ = driver.execute_query(
        "MATCH (r:Run {id: $id}) RETURN r.tool AS tool, r.config AS config, r.status AS status",
        id=extracted.run_id,
    )
    run = records[0]
    assert (run["tool"], run["status"]) == ("fake-llm", "succeeded")
    cfg = json.loads(run["config"])
    assert cfg["deployment"] == "fake-model"
    assert cfg["prompt"] == "extract-figures v1"
    assert cfg["prompt_sha256"] == config.extract_prompt().sha256
    assert (cfg["label_map"], cfg["label_map_sha256"]) == ("v1", config.label_map().sha256)
    assert cfg["parse_run"] == store.get_document(filing[0]).run.id
    assert cfg["pages"] == "2"


def test_re_extracting_supersedes_the_earlier_figures(store, filing, parser):
    extract(store, filing, parser, PageReadingLLM(FIGURES))
    first = {f.id for f in store.figures("MA0000011488")}
    extract(store, filing, parser, PageReadingLLM({"36 681": {}}))

    [current] = store.figures("MA0000011488")
    assert current.id not in first
    assert store.fact(next(iter(first))) is not None, "a superseded Fact keeps its link"


def test_a_failed_extraction_is_recorded_and_keeps_the_last_good_figures(store, filing, parser):
    extract(store, filing, parser, PageReadingLLM(FIGURES))
    with pytest.raises(ExtractFailed, match="recorded as failed run"):
        extract(store, filing, parser, PageReadingLLM(FIGURES, broken=True))

    assert len(store.figures("MA0000011488")) == 4


def test_re_parsing_supersedes_the_figures_of_the_old_parse(store, meta, parse, filing, parser):
    extract(store, filing, parser, PageReadingLLM(FIGURES))
    store.record_parse(meta, parse[0], parse_run(10), SHA)

    assert store.figures("MA0000011488") == []


def test_the_whole_filing_is_read_page_by_page(store, filing, parser):
    llm = PageReadingLLM(FIGURES)
    extract(store, filing, parser, llm)
    assert sorted(llm.pages) == ["Page 1", "Page 2"]


def test_an_unknown_document_fails(store, tmp_path, parser):
    with pytest.raises(LookupError):
        extract(store, ("nope", DocumentFiles(Path(tmp_path))), parser, PageReadingLLM({}))
