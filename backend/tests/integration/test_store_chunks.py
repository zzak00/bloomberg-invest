"""Contract tests for storing Chunks and Paragraphs (#21 AC2, AC5) against a real Neo4j."""

from datetime import UTC, datetime

import pytest
from conftest import make_run

from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep

SHA = "90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214"


def chunk_run(minute: int = 10, status: RunStatus = RunStatus.succeeded) -> RunInfo:
    return RunInfo(
        step=RunStep.chunk,
        tool="bloomberg-chunker",
        tool_version="0.1.0",
        config={"cap": "2000", "tokenizer": "cl100k_base"},
        started_at=datetime(2026, 11, 5, 9, minute, tzinfo=UTC),
        finished_at=datetime(2026, 11, 5, 9, minute + 1, tzinfo=UTC),
        status=status,
        error=None if status == RunStatus.succeeded else "ValueError: boom",
    )


@pytest.fixture
def document(store, meta, parsed):
    document_id = store.record_parse(meta, parsed, make_run(), SHA)
    detail = store.get_document(document_id)
    ids = {s.title: s.id for s in detail.sections}
    ids |= {c.title: c.id for s in detail.sections for c in s.children}
    return document_id, ids


def drafts(ids: dict[str, str]) -> list[ChunkDraft]:
    text = Block(kind="text", text="Voir note 2.", page=1, boxes=((1, 50.0, 100.0, 300.0, 120.0),))
    table = Block(kind="table", text="| a |\n| --- |\n| 1 |", page=2, last_page=3)
    return [
        ChunkDraft(
            index=0,
            kind="text",
            section_id=ids["1. RÉSULTATS"],
            paragraphs=(text,),
            text=text.text,
            token_count=4,
            pages=(1,),
            refers_to=(ids["2. VUE D'ENSEMBLE"],),
        ),
        ChunkDraft(
            index=1,
            kind="table",
            section_id=ids["1.1 En dirham"],
            paragraphs=(table,),
            text=table.text,
            token_count=9,
            pages=(2, 3),
            refers_to=(),
        ),
    ]


def current_chunks(driver, document_id):
    records, _, _ = driver.execute_query(
        """
        MATCH (k:Chunk)-[:FROM_DOCUMENT]->(:Document {id: $id})
        WHERE coalesce(k.superseded, false) = false
        OPTIONAL MATCH (k)-[:IN_SECTION]->(s:Section)
        OPTIONAL MATCH (k)-[:NEXT_CHUNK]->(next:Chunk)
        OPTIONAL MATCH (k)-[:REFERS_TO]->(note:Section)
        MATCH (k)-[:PRODUCED_BY]->(r:Run)
        CALL (k) { MATCH (k)-[:ON_PAGE]->(p:Page) RETURN collect(p.number) AS pages }
        CALL (k) {
            MATCH (n:Paragraph)-[:PART_OF]->(k)
            WHERE coalesce(n.superseded, false) = false
            RETURN collect(n {.text, .page, .boxes}) AS paragraphs
        }
        RETURN k.index AS index, k.kind AS kind, s.title AS section, next.index AS next,
               note.title AS refers_to, r.step AS step, r.id AS run, pages, paragraphs
        ORDER BY index
        """,
        id=document_id,
    )
    return [r.data() for r in records]


def test_chunks_are_linked_to_their_document_section_pages_notes_and_run(store, driver, document):
    document_id, ids = document
    run_id = store.record_chunks(document_id, drafts(ids), chunk_run())

    first, second = current_chunks(driver, document_id)
    assert (first["kind"], first["section"], first["pages"], first["next"]) == (
        "text",
        "1. RÉSULTATS",
        [1],
        1,
    )
    assert first["refers_to"] == "2. VUE D'ENSEMBLE"
    assert first["paragraphs"] == [
        {"text": "Voir note 2.", "page": 1, "boxes": [1.0, 50.0, 100.0, 300.0, 120.0]}
    ]
    assert (second["kind"], second["section"], sorted(second["pages"]), second["next"]) == (
        "table",
        "1.1 En dirham",
        [2, 3],
        None,
    )
    assert {first["run"], second["run"]} == {run_id}
    assert first["step"] == "chunk"


def test_re_chunking_supersedes_earlier_chunks_but_not_the_parse(store, driver, document):
    document_id, ids = document
    store.record_chunks(document_id, drafts(ids), chunk_run(10))
    latest = store.record_chunks(document_id, drafts(ids)[:1], chunk_run(20))

    chunks = current_chunks(driver, document_id)
    assert [(c["index"], c["run"]) for c in chunks] == [(0, latest)]
    records, _, _ = driver.execute_query(
        """
        MATCH (n)-[:SUPERSEDED_BY]->(:Run {id: $run})
        RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label
        """,
        run=latest,
    )
    assert [(r["label"], r["n"]) for r in records] == [("Chunk", 2), ("Paragraph", 2)]
    assert len(store.get_document(document_id).sections) == 2


def test_a_failed_chunk_run_is_recorded_and_keeps_the_last_good_chunks(store, driver, document):
    document_id, ids = document
    good = store.record_chunks(document_id, drafts(ids), chunk_run(10))
    store.record_chunks(document_id, [], chunk_run(20, RunStatus.failed))

    assert {c["run"] for c in current_chunks(driver, document_id)} == {good}
    records, _, _ = driver.execute_query(
        "MATCH (r:Run {step: 'chunk', status: 'failed'}) RETURN r.error AS error"
    )
    assert [r["error"] for r in records] == ["ValueError: boom"]


def test_re_parsing_supersedes_the_chunks_of_the_old_parse(store, driver, meta, parsed, document):
    document_id, ids = document
    store.record_chunks(document_id, drafts(ids), chunk_run())
    store.record_parse(meta, parsed, make_run(30), SHA)

    assert current_chunks(driver, document_id) == []


def test_chunks_for_an_unknown_document_fail(store):
    with pytest.raises(LookupError, match="no document nope"):
        store.record_chunks("nope", [], chunk_run())
