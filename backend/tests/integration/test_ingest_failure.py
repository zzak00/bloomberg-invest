"""A parse that fails still leaves a Run, so the failure is visible in the graph (ADR 0002)."""

import pytest
from conftest import FIXTURES
from fakes import BrokenParser, FakeEmbedder, WordCounter

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.service_layer.ingest import IngestFailed, ingest


def failed_runs(driver, document_id: str) -> list[tuple]:
    records, _, _ = driver.execute_query(
        "MATCH (r:Run)-[:PROCESSED]->(d:Document {id: $id}) "
        "RETURN r.status AS status, r.error AS error, r.tool AS tool, r.output AS output",
        id=document_id,
    )
    return [(r["status"], r["error"], r["tool"], r["output"]) for r in records]


def test_a_failed_parse_records_a_failed_run_and_raises(store, meta, tmp_path, driver):
    with pytest.raises(IngestFailed) as failure:
        ingest(
            FIXTURES / "filing.pdf",
            meta,
            store,
            DocumentFiles(tmp_path),
            BrokenParser(),
            WordCounter(),
            2000,
            FakeEmbedder(),
        )

    assert failed_runs(driver, failure.value.document_id) == [
        ("failed", "RuntimeError: the layout model crashed", "docling", None)
    ]
    assert isinstance(failure.value.__cause__, RuntimeError)


def test_a_parse_that_fails_after_saving_its_output_points_the_failed_run_to_it(
    store, meta, tmp_path, driver
):
    files = DocumentFiles(tmp_path)
    with pytest.raises(IngestFailed) as failure:
        ingest(
            FIXTURES / "filing.pdf",
            meta,
            store,
            files,
            BrokenParser(saves_output=True),
            WordCounter(),
            2000,
            FakeEmbedder(),
        )

    [(status, _, _, output)] = failed_runs(driver, failure.value.document_id)
    assert status == "failed"
    assert output.startswith("parses/") and (files.data_dir / output).exists()
