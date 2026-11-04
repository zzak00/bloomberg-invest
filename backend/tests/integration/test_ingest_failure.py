"""A parse that fails still leaves a Run, so the failure is visible in the graph (ADR 0002)."""

from pathlib import Path

import pytest
from conftest import FIXTURES

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.service_layer.ingest import IngestFailed, ingest


class BrokenParser:
    def __init__(self, saves_output: bool = False) -> None:
        self.tool = "docling"
        self.tool_version = "2.145.0"
        self.config = {"table_structure": "TableFormer v1"}
        self.saves_output = saves_output

    def parse(self, pdf: Path, output: Path):
        if self.saves_output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text("{}")
        raise RuntimeError("the layout model crashed")


def failed_runs(driver, document_id: str) -> list[tuple]:
    records, _, _ = driver.execute_query(
        "MATCH (r:Run)-[:PROCESSED]->(d:Document {id: $id}) "
        "RETURN r.status AS status, r.error AS error, r.tool AS tool, r.output AS output",
        id=document_id,
    )
    return [(r["status"], r["error"], r["tool"], r["output"]) for r in records]


def test_a_failed_parse_records_a_failed_run_and_raises(store, meta, tmp_path, driver):
    with pytest.raises(IngestFailed) as failure:
        ingest(FIXTURES / "filing.pdf", meta, store, DocumentFiles(tmp_path), BrokenParser())

    assert failed_runs(driver, failure.value.document_id) == [
        ("failed", "RuntimeError: the layout model crashed", "docling", None)
    ]
    assert isinstance(failure.value.__cause__, RuntimeError)


def test_a_parse_that_fails_after_saving_its_output_points_the_failed_run_to_it(
    store, meta, tmp_path, driver
):
    files = DocumentFiles(tmp_path)
    with pytest.raises(IngestFailed) as failure:
        ingest(FIXTURES / "filing.pdf", meta, store, files, BrokenParser(saves_output=True))

    [(status, _, _, output)] = failed_runs(driver, failure.value.document_id)
    assert status == "failed"
    assert output.startswith("parses/") and (files.data_dir / output).exists()
