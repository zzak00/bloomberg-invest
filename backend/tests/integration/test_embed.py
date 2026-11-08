"""Embedding a chunked Document (#21 AC2, AC5): an embed Run per call, against a real Neo4j."""

import json

import pytest
from fakes import FakeEmbedder
from test_store_search import chunk_run, drafts

from bloomberg_invest.service_layer.embed import EmbedFailed, embed_document


@pytest.fixture
def chunked(store, document):
    document_id, ids = document
    store.record_chunks(document_id, drafts(ids), chunk_run())
    return document_id


def embed_runs(driver, document_id):
    records, _, _ = driver.execute_query(
        """
        MATCH (r:Run {step: 'embed'})-[:PROCESSED]->(:Document {id: $id})
        RETURN r.id AS id, r.status AS status, r.tool AS tool, r.config AS config,
               r.error AS error
        ORDER BY r.started_at
        """,
        id=document_id,
    )
    return [r.data() for r in records]


def test_embedding_records_a_run_with_the_model_and_the_chunk_run_it_embedded(
    store, driver, chunked
):
    embedded = embed_document(chunked, store, FakeEmbedder())

    assert embedded.chunks == 2
    [run] = embed_runs(driver, chunked)
    assert (run["id"], run["status"], run["tool"]) == (embedded.run_id, "succeeded", "fake")
    assert json.loads(run["config"]) == {
        "model": "fake-embedder",
        "chunk_run": store.current_chunk_run(chunked),
    }


def test_search_finds_a_chunk_by_the_query_s_vector(store, chunked):
    embedder = FakeEmbedder()
    embed_document(chunked, store, embedder)
    units = dict(store.search_units(chunked))

    [hit] = store.search_vector(embedder.embed_query(next(iter(units.values()))), 1)
    assert hit == next(iter(units))


def test_a_failed_embedding_is_recorded_and_keeps_the_last_good_vectors(store, driver, chunked):
    good = embed_document(chunked, store, FakeEmbedder())

    with pytest.raises(EmbedFailed) as failure:
        embed_document(chunked, store, FakeEmbedder(broken=True))

    assert isinstance(failure.value.__cause__, RuntimeError)
    runs = embed_runs(driver, chunked)
    assert [r["status"] for r in runs] == ["succeeded", "failed"]
    assert runs[0]["id"] == good.run_id
    assert runs[1]["error"] == "RuntimeError: the model ran out of memory"


def test_a_document_with_no_chunks_is_not_embedded(store, document):
    document_id, _ = document
    embedder = FakeEmbedder()

    with pytest.raises(ValueError, match="no current chunks"):
        embed_document(document_id, store, embedder)
    assert embedder.calls == 0


def test_an_unknown_document_fails(store):
    with pytest.raises(LookupError, match="no document nope"):
        embed_document("nope", store, FakeEmbedder())
