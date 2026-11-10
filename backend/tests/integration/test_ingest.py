"""The ingest command end to end: PDF in, Document in Neo4j, PDF stored for the viewer."""

import hashlib
import re

import pytest
from conftest import FIXTURES, GOLDEN_PDF, GOLDEN_SHA
from fakes import FakeEmbedder, fake_extraction

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from transformers import AutoTokenizer

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser
from bloomberg_invest.adapters.tokens import TiktokenCounter
from bloomberg_invest.domain.chunking import Caps
from bloomberg_invest.service_layer.ingest import ingest
from bloomberg_invest.service_layer.search import search

# The app's default caps (settings.py).
CAPS = Caps(text=2000, table=1500)


def test_ingest_stores_the_pdf_and_records_the_parse(store, meta, tmp_path):
    files = DocumentFiles(tmp_path)
    ingested = ingest(
        FIXTURES / "filing.pdf",
        meta,
        store,
        files,
        DoclingParser(),
        TiktokenCounter(),
        CAPS,
        FakeEmbedder(),
        fake_extraction(),
    )
    document_id = ingested.document_id

    sha = hashlib.sha256((FIXTURES / "filing.pdf").read_bytes()).hexdigest()
    assert files.pdf_path(sha).read_bytes() == (FIXTURES / "filing.pdf").read_bytes()
    detail = store.get_document(document_id)
    assert detail.sha256 == sha
    assert detail.page_count == 2
    assert detail.run.tool_version == "2.145.0"
    assert detail.run.started_at < detail.run.finished_at
    assert detail.run.output.startswith(f"parses/{sha}/")
    assert (tmp_path / detail.run.output).stat().st_size > 0
    assert ingested.chunked.chunks > 0
    assert ingested.embedded.chunks == ingested.chunked.chunks, "every Chunk is embedded"


@pytest.mark.golden
@pytest.mark.embed
@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason=f"golden PDF not found at {GOLDEN_PDF}")
def test_the_golden_report_parses_into_its_outline_and_chunks_and_is_searchable(
    store, meta, tmp_path, driver
):
    assert hashlib.sha256(GOLDEN_PDF.read_bytes()).hexdigest() == GOLDEN_SHA
    files = DocumentFiles(tmp_path)
    counter = TiktokenCounter()
    embedder = bootstrap.EMBEDDERS["qwen3-0.6b"]()
    ingested = ingest(
        GOLDEN_PDF, meta, store, files, DoclingParser(), counter, CAPS, embedder, fake_extraction()
    )
    document_id = ingested.document_id

    detail = store.get_document(document_id)
    assert detail.page_count == 90
    assert detail.regulator == "AMMC"
    chapters = [s.title for s in detail.sections if re.match(r"\d+\. ", s.title)]
    assert [c[:2] for c in chapters] == ["1.", "2.", "3.", "4."]
    consolidated = next(s for s in detail.sections if s.title.startswith("3."))
    notes = [s.title for s in consolidated.children if s.title.startswith("NOTE")]
    assert len(notes) == 34
    assert notes[12].startswith("NOTE 13. DIVIDENDES")
    note_13 = next(s for s in consolidated.children if s.title.startswith("NOTE 13"))
    assert note_13.page == 54
    assert all(s.bbox for s in detail.sections)

    # Chunks (#21 AC1): every text Chunk fits the cap unless it is a single paragraph.
    records, _, _ = driver.execute_query(
        """
        MATCH (k:Chunk)-[:FROM_DOCUMENT]->(:Document {id: $id})
        OPTIONAL MATCH (k)-[:REFERS_TO]->(note:Section)
        RETURN k.id AS id, k.kind AS kind, k.token_count AS tokens,
               size(split(k.text, '\n\n')) AS paragraphs, count(note) AS notes
        """,
        id=document_id,
    )
    assert len(records) == ingested.chunked.chunks
    assert any(r["kind"] == "table" for r in records)
    assert all(r["tokens"] <= 2000 or r["paragraphs"] == 1 or r["kind"] == "table" for r in records)
    assert sum(r["notes"] for r in records) > 0, "some chunks cite a note"

    # Every Chunk fits the embedder's window, so none is cut (ADR 0004): long tables are split.
    tokenizer = AutoTokenizer.from_pretrained(embedder.name)
    texts = [i.text for i in store.embed_inputs(document_id)]
    longest = max(len(tokenizer(t)["input_ids"]) for t in texts)
    assert longest <= embedder.max_tokens, longest

    # Search (#21 AC3 asks for the top 5): "dividende proposé" ranks the p. 10 dividend first,
    # with its document, section path and page.
    first, *_ = hits = search("dividende proposé", 5, store, embedder)
    assert (first.pages, first.section_path[-1]) == ([10], "Dividende"), [
        (h.pages, h.section_path[-1:]) for h in hits
    ]
    assert "4,00 dirhams par action" in first.text
    assert first.document.id == document_id
