"""Search the filings: the current Chunks nearest the query's vector (#21, vector only)."""

from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.views import SearchHit


def search(query: str, limit: int, store: GraphStore, embedder: Embedder) -> list[SearchHit]:
    return store.hits(store.search_vector(embedder.embed_query(query), limit))
