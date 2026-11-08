"""Ingest chunks a filing (#21 AC1, AC2, AC5) on the chunking fixture, with Docling and Neo4j.

The cap is set low (200 tokens) so the fixture's long section must split.
"""

import pytest
from conftest import FIXTURES
from fakes import FakeEmbedder

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser
from bloomberg_invest.adapters.tokens import TiktokenCounter
from bloomberg_invest.service_layer.chunk import ChunkFailed, chunk_document
from bloomberg_invest.service_layer.ingest import ingest

CAP = 200
# The openings of the six paragraphs `make_chunking_fixture.py` writes twice under "2. VUE".
OVERVIEW = [
    "Le Groupe opère au Maroc et dans dix pays",
    "Au Maroc, le parc mobile progresse",
    "À l'international, les filiales poursuivent",
    "La concurrence reste vive",
    "Les investissements de l'exercice",
    "Le Groupe maintient une structure financière",
]


@pytest.fixture(scope="module")
def counter():
    return TiktokenCounter()


@pytest.fixture
def ingested(store, meta, tmp_path, counter):
    files = DocumentFiles(tmp_path)
    result = ingest(
        FIXTURES / "chunking.pdf", meta, store, files, DoclingParser(), counter, CAP, FakeEmbedder()
    )
    return result, files


def chunks(driver, document_id):
    records, _, _ = driver.execute_query(
        """
        MATCH (k:Chunk)-[:FROM_DOCUMENT]->(:Document {id: $id})
        WHERE coalesce(k.superseded, false) = false
        MATCH (k)-[:IN_SECTION]->(s:Section)
        OPTIONAL MATCH (k)-[:REFERS_TO]->(note:Section)
        CALL (k) { MATCH (k)-[:ON_PAGE]->(p:Page) RETURN collect(p.number) AS pages }
        MATCH (k)-[:PRODUCED_BY]->(r:Run)
        RETURN k.index AS index, k.kind AS kind, s.title AS section, k.token_count AS tokens,
               k.text AS text,
               note.title AS note, pages, r.id AS run
        ORDER BY index
        """,
        id=document_id,
    )
    return [r.data() for r in records]


def test_ingest_chunks_the_filing_by_its_structure(ingested, driver, counter):
    result, _ = ingested
    found = chunks(driver, result.document_id)

    assert len(found) == result.chunked.chunks
    tables = [c for c in found if c["kind"] == "table"]
    assert [(t["section"], sorted(t["pages"])) for t in tables] == [
        ("1. RÉSULTATS CONSOLIDÉS", [1, 2])
    ], "the table running onto page 2 is one Chunk"
    overview = [c for c in found if c["section"] == "2. VUE D'ENSEMBLE"]
    assert len(overview) > 1, "the long section splits"
    # A paragraph is never split, so only a lone paragraph may exceed the cap. A Chunk's text
    # joins its blocks with a blank line.
    blocks = [c["text"].split("\n\n") for c in overview]
    sizes = [[counter(b) for b in c] for c in blocks]
    assert all(c["tokens"] <= CAP or len(b) == 1 for c, b in zip(overview, blocks)), sizes
    # Docling cuts paragraphs differently per machine (#21), so check the text, not the count.
    text = " ".join(c["text"] for c in overview)
    assert all(text.count(p) == 2 for p in OVERVIEW), "no paragraph is lost"
    cites = {c["note"] for c in found if c["section"] == "1. RÉSULTATS CONSOLIDÉS"}
    assert "NOTE 2. DIVIDENDES" in cites
    assert {c["run"] for c in found} == {result.chunked.run_id}


def test_re_chunking_supersedes_the_earlier_chunks(ingested, store, driver, counter):
    result, files = ingested
    again = chunk_document(result.document_id, store, files, DoclingParser(), counter, CAP)

    assert again.chunks == result.chunked.chunks
    assert {c["run"] for c in chunks(driver, result.document_id)} == {again.run_id}


def test_a_chunking_failure_is_recorded_and_keeps_the_last_good_chunks(
    ingested, store, driver, counter
):
    result, files = ingested

    class Unreadable(DoclingParser):
        def read_blocks(self, output):
            raise RuntimeError("the saved output is unreadable")

    with pytest.raises(ChunkFailed) as failure:
        chunk_document(result.document_id, store, files, Unreadable(), counter, CAP)

    assert isinstance(failure.value.__cause__, RuntimeError)
    assert {c["run"] for c in chunks(driver, result.document_id)} == {result.chunked.run_id}
    records, _, _ = driver.execute_query(
        "MATCH (r:Run {id: $id}) RETURN r.status AS status, r.error AS error",
        id=failure.value.run_id,
    )
    assert records[0].data() == {
        "status": "failed",
        "error": "RuntimeError: the saved output is unreadable",
    }
