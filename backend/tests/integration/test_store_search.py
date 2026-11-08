"""Contract tests for indexing and searching Chunks (#21 AC2, AC3, AC5) against a real Neo4j."""

from datetime import UTC, datetime

import pytest
from test_store_chunks import chunk_run

from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep

DIMS = 8


def axis(i: int) -> list[float]:
    """A unit vector along one axis: the nearest stored vector is the one on the same axis."""
    return [1.0 if d == i else 0.0 for d in range(DIMS)]


def embed_run(minute: int = 30, status: RunStatus = RunStatus.succeeded) -> RunInfo:
    return RunInfo(
        step=RunStep.embed,
        tool="sentence-transformers",
        tool_version="5.1.0",
        config={"model": "Qwen/Qwen3-Embedding-0.6B"},
        started_at=datetime(2026, 11, 5, 9, minute, tzinfo=UTC),
        finished_at=datetime(2026, 11, 5, 9, minute + 1, tzinfo=UTC),
        status=status,
        error=None if status == RunStatus.succeeded else "RuntimeError: out of memory",
    )


def drafts(ids: dict[str, str]) -> list[ChunkDraft]:
    title = Block(kind="heading", text="1.1 En dirham", page=2)
    dividend = Block(
        kind="text",
        text="Le dividende proposé est de 4,00 dirhams par action.",
        page=2,
        boxes=((2, 50.0, 100.0, 300.0, 120.0),),
    )
    revenue = Block(
        kind="table",
        text="| | 2025 |\n| --- | --- |\n| Chiffre d'affaires | 36 802 |",
        page=3,
        header="| | 2025 |",
        rows=("| Chiffre d'affaires | 36 802 |",),
        columns=2,
    )
    return [
        ChunkDraft(
            index=0,
            kind="text",
            section_id=ids["1.1 En dirham"],
            paragraphs=(title, dividend),
            text=f"{title.text}\n\n{dividend.text}",
            token_count=12,
            pages=(2,),
            refers_to=(),
            path=("1. RÉSULTATS", "1.1 En dirham"),
        ),
        ChunkDraft(
            index=1,
            kind="table",
            section_id=ids["1.2 En euro"],
            paragraphs=(revenue,),
            text=revenue.text,
            token_count=10,
            pages=(3,),
            refers_to=(),
            path=("1. RÉSULTATS", "1.2 En euro"),
        ),
    ]


@pytest.fixture
def chunked(store, document):
    document_id, ids = document
    store.record_chunks(document_id, drafts(ids), chunk_run())
    return document_id, dict(store.search_units(document_id))


def embedded(store, document_id, units):
    """Each Chunk embedded along its own axis, in reading order."""
    vectors = {pid: axis(i) for i, pid in enumerate(units)}
    return store.record_embeddings(document_id, vectors, embed_run())


def test_every_chunk_is_a_search_unit_with_its_header_and_text(chunked):
    _, units = chunked

    assert list(units.values()) == [
        (
            "1. RÉSULTATS > 1.1 En dirham · p. 2\n1.1 En dirham\n\n"
            "Le dividende proposé est de 4,00 dirhams par action."
        ),
        "1. RÉSULTATS > 1.2 En euro · p. 3\nChiffre d'affaires: 2025 36 802",
    ]


def test_vector_search_returns_the_nearest_embedded_chunks(store, chunked):
    document_id, units = chunked
    dividend, revenue = units
    embedded(store, document_id, units)

    assert store.search_vector(axis(1), 1) == [revenue]
    assert store.search_vector(axis(0), 2) == [dividend, revenue]


def test_embeddings_are_recorded_with_their_run(store, driver, chunked):
    document_id, units = chunked
    run_id = embedded(store, document_id, units)

    records, _, _ = driver.execute_query(
        """
        MATCH (k:Chunk)-[:EMBEDDED_BY]->(r:Run)-[:PROCESSED]->(:Document {id: $id})
        RETURN r.id AS run, r.step AS step, count(k) AS chunks
        """,
        id=document_id,
    )
    assert [r.data() for r in records] == [{"run": run_id, "step": "embed", "chunks": 2}]


def test_re_embedding_supersedes_the_previous_embed_run(store, driver, chunked):
    document_id, units = chunked
    first = embedded(store, document_id, units)
    second = store.record_embeddings(
        document_id, {pid: axis(7 - i) for i, pid in enumerate(units)}, embed_run(40)
    )

    records, _, _ = driver.execute_query(
        """
        MATCH (:Chunk)-[:EMBEDDED_BY]->(r:Run) RETURN DISTINCT r.id AS run
        UNION
        MATCH (:Run {id: $first})-[:SUPERSEDED_BY]->(r:Run) RETURN r.id AS run
        """,
        first=first,
    )
    assert {r["run"] for r in records} == {second}
    assert store.search_vector(axis(7), 1) == [next(iter(units))]


def test_a_failed_embed_run_keeps_the_last_good_vectors(store, driver, chunked):
    document_id, units = chunked
    good = embedded(store, document_id, units)
    store.record_embeddings(document_id, {}, embed_run(40, RunStatus.failed))

    assert store.search_vector(axis(1), 1) == [list(units)[1]]
    records, _, _ = driver.execute_query("MATCH (:Chunk)-[:EMBEDDED_BY]->(r) RETURN r.id AS run")
    assert {r["run"] for r in records} == {good}


def test_embeddings_for_chunks_that_are_not_current_search_units_fail(store, chunked):
    document_id, _ = chunked
    with pytest.raises(ValueError, match="not current search units"):
        store.record_embeddings(document_id, {"nope": axis(0)}, embed_run())


def test_superseded_chunks_leave_the_index(store, document, chunked):
    document_id, ids = document
    _, old = chunked
    embedded(store, document_id, old)
    store.record_chunks(document_id, drafts(ids), chunk_run(20))

    current = dict(store.search_units(document_id))
    assert not set(current) & set(old)
    assert store.search_vector(axis(0), 5) == [], "the new Chunks are not embedded yet"


def test_hits_carry_document_section_path_pages_and_boxes_in_the_order_asked(store, chunked):
    document_id, units = chunked
    dividend, revenue = units

    first, second = store.hits([revenue, dividend])

    assert (first.chunk_id, second.chunk_id) == (revenue, dividend)
    assert second.text == "1.1 En dirham\n\nLe dividende proposé est de 4,00 dirhams par action."
    assert second.section_path == ["1. RÉSULTATS", "1.1 En dirham"]
    assert (second.pages, second.boxes) == ([2], [(2, 50.0, 100.0, 300.0, 120.0)])
    assert second.document.id == document_id
    assert second.document.issuer.name == "Maroc Telecom"
    assert first.section_path == ["1. RÉSULTATS", "1.2 En euro"]
