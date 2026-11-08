"""Contract tests for the graph store against a real Neo4j."""

import pytest
from conftest import make_run

from bloomberg_invest.domain.model import ParsedDocument, RunStatus

SHA = "90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214"


def titles(sections) -> list[str]:
    return [s.title for s in sections]


def test_schema_creates_the_uniqueness_constraints(store, driver):
    records, _, _ = driver.execute_query("SHOW CONSTRAINTS YIELD labelsOrTypes, properties")
    found = {(r["labelsOrTypes"][0], r["properties"][0]) for r in records}
    assert {
        ("Document", "id"),
        ("Document", "sha256"),
        ("Run", "id"),
        ("Organisation", "isin"),
        ("Section", "id"),
        ("Chunk", "id"),
        ("Paragraph", "id"),
    } <= found


def test_a_recorded_parse_is_listed_with_its_issuer(store, meta, parsed):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)

    [summary] = store.list_documents()
    assert summary.id == document_id
    assert summary.issuer.name == "Maroc Telecom"
    assert summary.issuer.isin == "MA0000011488"
    assert (summary.doc_type, summary.fiscal_year, summary.regulator) == (
        "annual_report",
        2025,
        "AMMC",
    )
    assert summary.page_count == 3


def test_the_document_keeps_its_pages_and_section_tree(store, meta, parsed):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)

    detail = store.get_document(document_id)
    assert detail.sha256 == SHA
    assert [(p.number, p.width, p.height) for p in detail.pages] == [
        (n, 595.0, 842.0) for n in (1, 2, 3)
    ]
    assert titles(detail.sections) == ["1. RÉSULTATS", "2. VUE D'ENSEMBLE"]
    first = detail.sections[0]
    assert titles(first.children) == ["1.1 En dirham", "1.2 En euro"]
    assert (first.level, first.page, first.bbox) == (1, 1, (50, 60, 300, 80))
    assert first.children[1].bbox is None
    assert all(s.id for s in [first, *first.children])


def test_every_page_and_section_links_to_the_run_that_produced_it(store, meta, parsed, driver):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)

    records, _, _ = driver.execute_query(
        """
        MATCH (d:Document {id: $id})
        MATCH (d)-[:HAS_PAGE|HAS_SECTION*]->(n)
        OPTIONAL MATCH (n)-[:PRODUCED_BY]->(r:Run {step: 'parse'})-[:PROCESSED]->(d)
        RETURN count(n) AS nodes, count(r) AS linked
        """,
        id=document_id,
    )
    assert records[0]["nodes"] == 3 + 4
    assert records[0]["linked"] == records[0]["nodes"]

    run = store.get_document(document_id).run
    assert (run.step, run.tool, run.tool_version, run.status) == (
        "parse",
        "docling",
        "2.145.0",
        "succeeded",
    )
    assert run.config == {"table_structure": "TableFormer v1"}
    assert run.output == "parses/90e8b73c/20261103T090000Z-docling.json"
    assert run.started_at < run.finished_at


def test_the_document_and_organisation_link_to_the_run_that_created_them(
    store, meta, parsed, driver
):
    store.record_parse(meta, parsed, make_run(0), SHA)
    store.record_parse(meta, parsed, make_run(10), SHA)

    records, _, _ = driver.execute_query(
        """
        MATCH (n) WHERE n:Document OR n:Organisation
        OPTIONAL MATCH (n)-[:PRODUCED_BY]->(r:Run)
        RETURN labels(n)[0] AS label, n.superseded AS superseded,
               collect(r.started_at.minute) AS runs
        ORDER BY label
        """
    )
    # Matched again on re-ingest, not created again: still linked to the first Run only,
    # and never superseded.
    assert [(r["label"], r["superseded"], r["runs"]) for r in records] == [
        ("Document", None, [0]),
        ("Organisation", None, [0]),
    ]


def test_a_section_sits_on_its_page(store, meta, parsed, driver):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)

    records, _, _ = driver.execute_query(
        "MATCH (:Document {id: $id})-[:HAS_SECTION*]->(s)-[:ON_PAGE]->(p:Page) "
        "RETURN s.title AS title, p.number AS page ORDER BY title",
        id=document_id,
    )
    assert [(r["title"], r["page"]) for r in records] == [
        ("1. RÉSULTATS", 1),
        ("1.1 En dirham", 2),
        ("1.2 En euro", 3),
        ("2. VUE D'ENSEMBLE", 3),
    ]


def test_re_ingesting_the_same_pdf_supersedes_the_previous_run(store, meta, parsed, driver):
    first_id = store.record_parse(meta, parsed, make_run(0), SHA)
    reparsed = parsed.model_copy(update={"sections": parsed.sections[:1]})
    second_id = store.record_parse(meta, reparsed, make_run(10), SHA)

    assert second_id == first_id
    assert len(store.list_documents()) == 1
    detail = store.get_document(first_id)
    assert titles(detail.sections) == ["1. RÉSULTATS"]
    assert detail.run.started_at.minute == 10
    assert len(detail.pages) == 3

    records, _, _ = driver.execute_query(
        """
        MATCH (old {superseded: true})-[:SUPERSEDED_BY]->(r:Run)
        RETURN count(old) AS superseded, collect(DISTINCT r.started_at.minute) AS by
        """
    )
    assert records[0]["superseded"] == 3 + 4
    assert records[0]["by"] == [10]


def test_an_unknown_document_is_none(store):
    assert store.get_document("no-such-id") is None


def test_a_failed_parse_is_recorded_but_not_shown(store, meta, driver):
    failed = make_run(0).model_copy(
        update={"status": RunStatus.failed, "error": "RuntimeError: boom"}
    )
    document_id = store.record_failed_parse(meta, failed, SHA)

    assert store.list_documents() == []
    assert store.get_document(document_id) is None
    records, _, _ = driver.execute_query(
        """
        MATCH (r:Run)-[:PROCESSED]->(d:Document {id: $id})
        RETURN r.status AS status, r.error AS error, COUNT { (d)-[:HAS_PAGE]->() } AS pages
        """,
        id=document_id,
    )
    assert [(r["status"], r["error"], r["pages"]) for r in records] == [
        ("failed", "RuntimeError: boom", 0)
    ]


def test_a_failed_re_ingest_keeps_the_last_good_parse(store, meta, parsed, driver):
    document_id = store.record_parse(meta, parsed, make_run(0), SHA)
    failed = make_run(10).model_copy(
        update={"status": RunStatus.failed, "error": "RuntimeError: boom"}
    )
    assert store.record_failed_parse(meta, failed, SHA) == document_id

    detail = store.get_document(document_id)
    assert detail.run.started_at.minute == 0
    assert titles(detail.sections) == ["1. RÉSULTATS", "2. VUE D'ENSEMBLE"]
    [summary] = store.list_documents()
    assert summary.ingested_at == detail.run.finished_at
    records, _, _ = driver.execute_query("MATCH (n {superseded: true}) RETURN count(n) AS n")
    assert records[0]["n"] == 0


def test_a_section_without_its_page_fails_the_whole_parse(store, meta, parsed):
    # Bypasses the domain check to prove the store never drops a section silently.
    broken = ParsedDocument.model_construct(pages=parsed.pages[:1], sections=parsed.sections)

    with pytest.raises(ValueError, match="1.1 En dirham.*page 2"):
        store.record_parse(meta, broken, make_run(), SHA)
    assert store.list_documents() == []
