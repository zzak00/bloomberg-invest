"""Contract tests for indexing and searching Chunks (#21 AC2, AC3, AC5) against a real Neo4j."""

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from conftest import SHA, make_run
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
            table=3,
            part=1,
            parts=1,
        ),
    ]


def embed_texts(store, document_id) -> dict[str, str]:
    """The Document's current Chunks to embed: index text by Chunk id, in reading order."""
    return {i.chunk_id: i.text for i in store.embed_inputs(document_id)}


@pytest.fixture
def chunked(store, document):
    document_id, ids = document
    store.record_chunks(document_id, drafts(ids), chunk_run())
    return document_id, embed_texts(store, document_id)


def embedded(store, document_id, units):
    """Each Chunk embedded along its own axis, in reading order."""
    vectors = {chunk_id: axis(i) for i, chunk_id in enumerate(units)}
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


def embed_state(driver, document_id):
    """The Document's embed Runs, oldest first, and how many of its Chunks have a vector."""
    runs, _, _ = driver.execute_query(
        """
        MATCH (r:Run {step: 'embed'})-[:PROCESSED]->(:Document {id: $id})
        OPTIONAL MATCH (r)-[:SUPERSEDED_BY]->(by:Run)
        RETURN r.id AS run, r.status AS status, by.id AS superseded_by ORDER BY r.started_at
        """,
        id=document_id,
    )
    [vectors], _, _ = driver.execute_query(
        "MATCH (k:Chunk)-[:FROM_DOCUMENT]->(:Document {id: $id}) RETURN count(k.embedding) AS n",
        id=document_id,
    )
    return [r.data() for r in runs], vectors["n"]


def test_an_embed_run_on_the_document_gives_every_chunk_a_vector(store, driver, chunked):
    document_id, units = chunked
    run_id = embedded(store, document_id, units)

    runs, vectors = embed_state(driver, document_id)
    assert runs == [{"run": run_id, "status": "succeeded", "superseded_by": None}]
    assert vectors == 2
    [links], _, _ = driver.execute_query(
        "MATCH (:Chunk)-[l]->(:Run {id: $id}) RETURN count(l) AS n", id=run_id
    )
    assert links["n"] == 0, "the Run links to the Document, not to each Chunk"


def test_re_embedding_supersedes_the_previous_embed_run(store, driver, chunked):
    document_id, units = chunked
    first = embedded(store, document_id, units)
    second = store.record_embeddings(
        document_id, {chunk_id: axis(7 - i) for i, chunk_id in enumerate(units)}, embed_run(40)
    )

    runs, _ = embed_state(driver, document_id)
    assert runs == [
        {"run": first, "status": "succeeded", "superseded_by": second},
        {"run": second, "status": "succeeded", "superseded_by": None},
    ]
    assert store.search_vector(axis(7), 1) == [next(iter(units))], "the vectors are replaced"


def test_a_failed_embed_run_keeps_the_last_good_vectors(store, driver, chunked):
    document_id, units = chunked
    good = embedded(store, document_id, units)
    store.record_embeddings(document_id, {}, embed_run(40, RunStatus.failed))

    assert store.search_vector(axis(1), 1) == [list(units)[1]]
    runs, _ = embed_state(driver, document_id)
    assert [(r["run"] == good, r["status"], r["superseded_by"]) for r in runs] == [
        (True, "succeeded", None),
        (False, "failed", None),
    ]


def test_embeddings_for_chunks_that_are_not_current_fail(store, chunked):
    document_id, units = chunked
    vectors = {chunk_id: axis(i) for i, chunk_id in enumerate(units)} | {"nope": axis(5)}
    with pytest.raises(ValueError, match="1 ids are not current Chunks"):
        store.record_embeddings(document_id, vectors, embed_run())


def test_an_embed_run_must_cover_every_current_chunk(store, driver, chunked):
    document_id, units = chunked
    with pytest.raises(ValueError, match="1 current ones have no vector"):
        store.record_embeddings(document_id, {next(iter(units)): axis(0)}, embed_run())

    assert embed_state(driver, document_id) == ([], 0), "nothing is written, the Run included"


def test_superseded_chunks_leave_the_index(store, document, chunked):
    document_id, ids = document
    _, old = chunked
    embedded(store, document_id, old)
    store.record_chunks(document_id, drafts(ids), chunk_run(20))

    current = embed_texts(store, document_id)
    assert not set(current) & set(old)
    assert store.search_vector(axis(0), 5) == [], "the new Chunks are not embedded yet"


def test_a_re_chunk_supersedes_the_embed_run_of_the_old_chunks(store, driver, document, chunked):
    document_id, ids = document
    _, old = chunked
    stale = embedded(store, document_id, old)
    rechunk = store.record_chunks(document_id, drafts(ids), chunk_run(20))

    runs, vectors = embed_state(driver, document_id)
    assert runs == [{"run": stale, "status": "succeeded", "superseded_by": rechunk}]
    assert vectors == 0


def test_a_re_parse_supersedes_the_embed_run_of_the_old_chunks(
    store, driver, meta, parsed, chunked
):
    document_id, units = chunked
    stale = embedded(store, document_id, units)
    store.record_parse(meta, parsed, make_run(30), SHA)

    runs, vectors = embed_state(driver, document_id)
    [run] = runs
    assert run["run"] == stale
    assert run["superseded_by"] is not None, "the re-parse supersedes it"
    assert vectors == 0


def test_an_embed_after_a_re_chunk_is_the_only_current_embed_run(store, driver, document, chunked):
    document_id, ids = document
    _, old = chunked
    embedded(store, document_id, old)
    rechunk = store.record_chunks(document_id, drafts(ids), chunk_run(20))
    fresh = embedded(store, document_id, embed_texts(store, document_id))

    [current], _, _ = driver.execute_query(
        """
        MATCH (r:Run {step: 'embed'})-[:PROCESSED]->(:Document {id: $id})
        WHERE coalesce(r.superseded, false) = false
        RETURN collect(r.id) AS ids
        """,
        id=document_id,
    )
    assert current["ids"] == [fresh]
    assert store.current_chunk_run(document_id) == rechunk


def test_chunks_carry_kind_document_section_path_pages_and_boxes_in_the_order_asked(store, chunked):
    document_id, units = chunked
    dividend, revenue = units

    first, second = store.chunks([revenue, dividend])

    assert (first.id, second.id) == (revenue, dividend)
    assert second.text == "1.1 En dirham\n\nLe dividende proposé est de 4,00 dirhams par action."
    assert second.section_path == ["1. RÉSULTATS", "1.1 En dirham"]
    assert second.pages == [2]
    assert [b.model_dump() for b in second.boxes] == [
        {"page": 2, "left": 50.0, "top": 100.0, "right": 300.0, "bottom": 120.0}
    ]
    assert second.document.id == document_id
    assert second.document.issuer.name == "Maroc Telecom"
    assert first.section_path == ["1. RÉSULTATS", "1.2 En euro"]
    assert (first.kind, second.kind) == ("table", "text")
    assert (first.table.part, first.table.parts) == (1, 1)
    assert second.table is None


def test_the_parts_of_a_split_table_share_one_table_id(store, document):
    document_id, ids = document
    _, revenue = drafts(ids)
    parts = [replace(revenue, index=1 + n, part=1 + n, parts=2) for n in range(2)]
    store.record_chunks(document_id, parts, chunk_run())

    first, second = store.chunks(list(embed_texts(store, document_id)))
    assert first.table.table_id == second.table.table_id
    assert [(c.table.part, c.table.parts) for c in (first, second)] == [(1, 2), (2, 2)]
