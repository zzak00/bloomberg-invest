"""The ingest command end to end: PDF in, Document in Neo4j, PDF stored for the viewer."""

import hashlib
import os
import re
from pathlib import Path

import pytest
from conftest import FIXTURES

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest.files import DocumentFiles
from bloomberg_invest.ingest.cli import ingest
from bloomberg_invest.parsing.docling_parser import DoclingParser

GOLDEN_PDF = Path(
    os.environ.get(
        "GOLDEN_PDF", Path(__file__).parents[2] / "data" / "inbox" / "Maroc_Telecom_RFA_2025.pdf"
    )
)
GOLDEN_SHA = "90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214"


def test_ingest_stores_the_pdf_and_records_the_parse(store, meta, tmp_path):
    files = DocumentFiles(tmp_path)
    document_id = ingest(FIXTURES / "filing.pdf", meta, store, files, DoclingParser())

    sha = hashlib.sha256((FIXTURES / "filing.pdf").read_bytes()).hexdigest()
    assert files.pdf_path(sha).read_bytes() == (FIXTURES / "filing.pdf").read_bytes()
    detail = store.get_document(document_id)
    assert detail.sha256 == sha
    assert detail.page_count == 2
    assert detail.run.tool_version == "2.145.0"
    assert detail.run.started_at < detail.run.finished_at
    assert detail.run.output.startswith(f"parses/{sha}/")
    assert (tmp_path / detail.run.output).stat().st_size > 0


@pytest.mark.golden
@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason=f"golden PDF not found at {GOLDEN_PDF}")
def test_the_golden_report_parses_into_its_outline(store, meta, tmp_path):
    assert hashlib.sha256(GOLDEN_PDF.read_bytes()).hexdigest() == GOLDEN_SHA
    document_id = ingest(GOLDEN_PDF, meta, store, DocumentFiles(tmp_path), DoclingParser())

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
