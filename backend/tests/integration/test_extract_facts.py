"""Extracting the eight other kinds of fact from a parsed filing, and linking their names (#24 AC1,
AC2). The fixture PDF is parsed once by Docling; the LLM is a fake that answers from the page it
is shown, so the real page rendering, check, quote boxes, store and linking run without a live
model."""

import hashlib
import shutil
from datetime import UTC, datetime

import pytest
from conftest import FIXTURES
from fakes import FactReadingLLM

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest import config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser
from bloomberg_invest.domain.model import RunInfo, RunStep
from bloomberg_invest.service_layer.facts import FactExtraction, FactsFailed, extract_facts
from bloomberg_invest.service_layer.names import link_names

SHA = hashlib.sha256((FIXTURES / "filing.pdf").read_bytes()).hexdigest()
OUTPUT = f"parses/{SHA}/20261112T090000Z-docling.json"
# The fixture's page 2 proposes a dividend: "le Conseil propose un dividende de 4,01 dirhams par
# action". The Group is the filing's issuer.
DIVIDEND = {
    "company": {"written": "le Groupe", "name": "Maroc Telecom", "kind": "company"},
    "measure": "per_share",
    "amount": "4,01",
    "unit": "MAD",
    "status": "proposed",
    "fiscal_year": 2025,
    "quote": "le Conseil propose un dividende de 4,01 dirhams par action",
}
MISREAD = DIVIDEND | {"amount": "4,10"}


class BrokenLLM(FactReadingLLM):
    def complete_json(self, system, user, schema_name, schema):
        raise RuntimeError("the deployment answered 429 Too Many Requests")


@pytest.fixture(scope="module")
def parse(tmp_path_factory):
    data = tmp_path_factory.mktemp("data")
    (data / OUTPUT).parent.mkdir(parents=True)
    files = DocumentFiles(data)
    files.pdf_path(SHA).parent.mkdir(parents=True)
    shutil.copy(FIXTURES / "filing.pdf", files.pdf_path(SHA))
    parser = DoclingParser()
    return parser, parser.parse(FIXTURES / "filing.pdf", data / OUTPUT), data


@pytest.fixture
def filing(store, meta, parse):
    parser, parsed, data = parse
    run = RunInfo(
        step=RunStep.parse,
        tool="docling",
        tool_version="2.145.0",
        config={},
        started_at=datetime(2026, 11, 12, 9, tzinfo=UTC),
        finished_at=datetime(2026, 11, 12, 9, 1, tzinfo=UTC),
        output=OUTPUT,
    )
    return store.record_parse(meta, parsed, run, SHA), DocumentFiles(data), parser


def extract(store, filing, llm):
    document_id, files, parser = filing
    extraction = FactExtraction(llm, config.facts_prompt(), concurrency=2)
    return extract_facts(document_id, store, files, parser, extraction)


def test_every_page_is_read_and_a_stated_fact_cites_the_words_it_is_read_from(store, filing):
    llm = FactReadingLLM({"dividend": [DIVIDEND, MISREAD]})
    extracted = extract(store, filing, llm)
    assert (extracted.pages, extracted.facts, extracted.rejected) == (2, 1, 1)
    assert sorted(llm.pages) == ["Page 1", "Page 2"]
    [fact], [rejected] = store.facts()
    assert (fact.kind, fact.values["amount"], fact.amount_value, fact.currency) == (
        "dividend",
        "4,01",
        "4.01",
        "MAD",
    )
    assert (fact.fiscal_year, fact.period_end.isoformat()) == (2025, "2025-12-31")
    # Boxed by its quote in the PDF's text layer, not by its whole paragraph.
    assert fact.passage.kind == "span" and fact.page == 2
    assert len(fact.passage.boxes) >= 1
    assert all(b.page == 2 for b in fact.passage.boxes)
    assert rejected.reason == "a number it states is not in its quote"


def test_the_issuer_s_name_links_to_it_and_the_run_records_what_it_used(store, filing, driver):
    document_id, _, _ = filing
    extracted = extract(store, filing, FactReadingLLM({"dividend": [DIVIDEND]}))
    linked = link_names(document_id, store)
    assert (linked.linked, linked.to_check) == (1, 0)
    [fact], _ = store.facts("MA0000011488")
    assert fact.parties[0].entity.isin == "MA0000011488"
    assert fact.parties[0].written == "le Groupe"
    records, _, _ = driver.execute_query(
        "MATCH (r:Run {id: $id}) RETURN r.config AS config", id=extracted.run_id
    )
    assert '"prompt": "extract-facts v1"' in records[0]["config"]


def test_a_failed_extraction_is_recorded_and_keeps_the_last_good_facts(store, filing):
    extract(store, filing, FactReadingLLM({"dividend": [DIVIDEND]}))
    with pytest.raises(FactsFailed):
        extract(store, filing, BrokenLLM())
    facts, _ = store.facts()
    assert [f.values["amount"] for f in facts] == ["4,01"]
