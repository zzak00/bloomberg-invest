"""The Embedder contract, on the fake and on the real model: unit vectors of one size, in order."""

import math

import pytest
from fakes import FakeEmbedder

from bloomberg_invest.adapters.embedding import Embedder

TEXTS = ["Le dividende proposé.", "Le chiffre d'affaires.", "Néant."]


def real(name: str):
    def build() -> Embedder:
        pytest.importorskip("sentence_transformers")
        from bloomberg_invest import bootstrap

        return bootstrap.EMBEDDERS[name]()

    return pytest.param(build, id=name, marks=pytest.mark.embed)


# The Embedder contract: every test here runs on each implementation listed.
@pytest.fixture(scope="module", params=[pytest.param(FakeEmbedder, id="fake"), real("qwen3-0.6b")])
def embedder(request) -> Embedder:
    return request.param()


def dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_documents_and_queries_are_unit_vectors_of_one_size(embedder):
    documents = embedder.embed_documents(TEXTS)
    query = embedder.embed_query("proposed dividend")

    assert len(documents) == len(TEXTS)
    assert {len(v) for v in [*documents, query]} == {len(query)}
    # Half-precision kernels on Apple GPUs leave the norms within half a percent of 1.
    assert all(math.isclose(dot(v, v), 1.0, abs_tol=1e-2) for v in [*documents, query])


def test_a_batch_keeps_the_order_of_its_texts(embedder):
    batch = embedder.embed_documents(TEXTS)
    one_by_one = [embedder.embed_documents([t])[0] for t in TEXTS]

    assert all(dot(a, b) > 0.99 for a, b in zip(batch, one_by_one, strict=True))


def test_no_texts_give_no_vectors(embedder):
    assert embedder.embed_documents([]) == []


# Beyond the contract: the real model ranks by meaning, across languages. The fake matches words.
@pytest.fixture(scope="module", params=[real("qwen3-0.6b")])
def model(request) -> Embedder:
    return request.param()


def test_an_english_query_is_nearest_the_french_passage_that_answers_it(model):
    dividend, revenue = model.embed_documents(
        [
            "Le Conseil proposera un dividende de 4,00 dirhams par action.",
            "Le chiffre d'affaires consolidé atteint 36 802 millions de dirhams.",
        ]
    )
    query = model.embed_query("What dividend per share is proposed?")

    assert dot(query, dividend) > dot(query, revenue)


def test_a_text_past_the_window_is_cut_not_refused(embedder):
    long = " ".join(["dividende"] * (4 * embedder.max_tokens))

    [vector] = embedder.embed_documents([long])
    assert math.isclose(dot(vector, vector), 1.0, abs_tol=1e-2)
