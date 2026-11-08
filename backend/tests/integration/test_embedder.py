"""The Embedder contract against the real model: unit vectors that rank by meaning."""

import math

import pytest

from bloomberg_invest.adapters.embedding import Embedder

pytestmark = pytest.mark.embed


@pytest.fixture(scope="module", params=["qwen3-0.6b"])
def embedder(request) -> Embedder:
    pytest.importorskip("sentence_transformers")
    from bloomberg_invest import bootstrap

    return bootstrap.EMBEDDERS[request.param]()


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_documents_and_queries_are_unit_vectors_of_one_size(embedder):
    documents = embedder.embed_documents(["Le dividende proposé.", "Le chiffre d'affaires."])
    query = embedder.embed_query("proposed dividend")

    assert len(documents) == 2
    assert {len(v) for v in [*documents, query]} == {len(query)}
    # Half-precision kernels on Apple GPUs leave the norms within half a percent of 1.
    assert all(math.isclose(dot(v, v), 1.0, abs_tol=1e-2) for v in [*documents, query])


def test_an_english_query_is_nearest_the_french_paragraph_that_answers_it(embedder):
    dividend, revenue = embedder.embed_documents(
        [
            "Le Conseil proposera un dividende de 4,00 dirhams par action.",
            "Le chiffre d'affaires consolidé atteint 36 802 millions de dirhams.",
        ]
    )
    query = embedder.embed_query("What dividend per share is proposed?")

    assert dot(query, dividend) > dot(query, revenue)
