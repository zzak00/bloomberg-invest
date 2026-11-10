"""The golden harness for figures (#22 AC5): ingest golden v0, extract with the LLM's answers
replayed, and score against `figures.csv` as #10 scored the extractors.

A golden figure is correct when a Fact on its page has the same fiscal year, scope, line item and
number: the check already passed, or it would not be a Fact. #10 measured 148 of 158.

The answers come from a recording next to the golden PDF (`data/recordings/`, never committed:
it is derived from the AMMC report). Record it once, live, on the machine that parses:

    LLM_RECORD=1 uv run --extra ingest --env-file <secrets> pytest -m golden -s \\
        tests/integration/test_golden_figures.py
"""

import csv
import os
from collections import Counter

import pytest
from conftest import GOLDEN, GOLDEN_PDF, GOLDEN_SHA, azure_settings
from fakes import FakeEmbedder

pytestmark = [pytest.mark.ingest, pytest.mark.golden]
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest import bootstrap, config
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.llm.recording import RecordingLLM, ReplayLLM
from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser
from bloomberg_invest.adapters.tokens import TiktokenCounter
from bloomberg_invest.domain.chunking import Caps
from bloomberg_invest.domain.figures import number
from bloomberg_invest.service_layer.extract import Extraction
from bloomberg_invest.service_layer.ingest import ingest

# Named like the notebook's recording, so both replay the same answers.
RECORDING = GOLDEN_PDF.parents[1] / "recordings" / f"{GOLDEN_SHA[:12]}-extract-figures-v1.jsonl"
# No text layer (p. 26) or unreadable (p. 58) in golden v0, as in #10.
EXCLUDED_PAGES = {26, 58}
TARGET = 148


def fiscal_year(period: str) -> int:
    """FY2025 and 2025-12-31 are both fiscal year 2025."""
    return int(period[2:]) if period.startswith("FY") else int(period[:4])


def golden_figures() -> list[dict]:
    with (GOLDEN / "figures.csv").open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return [
        r | {"page": int(r["page"]), "year": fiscal_year(r["period"])}
        for r in rows
        if r["page"].isdigit() and int(r["page"]) not in EXCLUDED_PAGES and r["period"]
    ]


def extraction() -> Extraction:
    """Live and recording with LLM_RECORD set, replaying otherwise."""
    if os.environ.get("LLM_RECORD"):
        llm = RecordingLLM(bootstrap.llm(azure_settings()), RECORDING)
    elif RECORDING.exists():
        llm = ReplayLLM(RECORDING)
    else:
        pytest.skip(f"no recording at {RECORDING}; record it once with LLM_RECORD=1")
    return Extraction(llm, config.label_map(), config.extract_prompt(), concurrency=4)


def outcome(golden: dict, facts: list, rejected: list[dict]) -> str:
    def same_value(f_page, f_year, f_value) -> bool:
        return (f_page, f_year, number(f_value)) == (
            golden["page"],
            golden["year"],
            number(golden["value_as_written"]),
        )

    same = [f for f in facts if same_value(f.passage.page, f.fiscal_year, f.value_as_written)]
    labelled = [
        f
        for f in same
        if (f.line_item, f.basis_scope) == (golden["line_item"], golden["basis_scope"])
    ]
    if labelled:
        return "correct"
    if any(
        same_value(r["page"], r["fiscal_year"], r["value"])
        and (r["line_item"], r["scope"]) == (golden["line_item"], golden["basis_scope"])
        for r in rejected
    ):
        return "rejected by the check"
    return "wrong label" if same else "missing"


@pytest.mark.skipif(not GOLDEN_PDF.exists(), reason=f"golden PDF not found at {GOLDEN_PDF}")
def test_golden_figures_are_extracted_as_well_as_in_the_bake_off(store, meta, tmp_path, driver):
    ingested = ingest(
        GOLDEN_PDF,
        meta,
        store,
        DocumentFiles(tmp_path),
        DoclingParser(),
        TiktokenCounter(),
        Caps(text=2000, table=1500),
        FakeEmbedder(),
        extraction(),
    )

    facts, _ = store.figures("MA0000011488")
    records, _, _ = driver.execute_query(
        """
        MATCH (n:RejectedFigure)-[:PRODUCED_BY]->(:Run {id: $run})
        RETURN n.page AS page, n.fiscal_year AS fiscal_year, n.value_as_written AS value,
               n.line_item AS line_item, n.basis_scope AS scope, n.reason AS reason
        """,
        run=ingested.extracted.run_id,
    )
    rejected = [dict(r) for r in records]
    golden = golden_figures()
    results = [(g, outcome(g, facts, rejected)) for g in golden]
    counts = Counter(o for _, o in results)

    print(
        f"\n{ingested.extracted.pages} pages, {ingested.extracted.figures} figures, "
        f"{ingested.extracted.rejected} rejected by the check; golden: {dict(counts)}"
    )
    print("| Outcome | Page | Line item | Scope | Year | Value | Label in report |")
    print("| --- | --- | --- | --- | --- | --- | --- |")
    for g, o in results:
        if o != "correct":
            print(
                f"| {o} | {g['page']} | {g['line_item']} | {g['basis_scope']} | {g['year']} "
                f"| {g['value_as_written']} | {g['raw_label']} |"
            )
    for reason, n in Counter(r["reason"] for r in rejected).items():
        print(f"rejected, {reason}: {n}")

    assert len(golden) == 158
    assert counts["correct"] >= TARGET, dict(counts)
