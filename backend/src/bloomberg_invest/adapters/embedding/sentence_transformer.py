"""Embedding with an open model run locally by sentence-transformers (#21: Qwen3-Embedding-0.6B)."""

from importlib.metadata import version

from bloomberg_invest.adapters.embedding import Embedder

# Long tables are cut for the vector; their full text stays in the full-text index.
MAX_TOKENS = 1024


class SentenceTransformerEmbedder(Embedder):
    tool = "sentence-transformers"

    def __init__(self, name: str, query_prompt: str | None = None, batch_size: int = 16) -> None:
        # Imported here so code that never embeds runs without torch installed.
        from sentence_transformers import SentenceTransformer

        self.name = name
        self.tool_version = version("sentence-transformers")
        self._query_prompt = query_prompt
        self._batch_size = batch_size
        self._model = SentenceTransformer(name)
        self._model.max_seq_length = MAX_TOKENS

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        kwargs = {"prompt_name": self._query_prompt} if self._query_prompt else {}
        return self._model.encode([text], normalize_embeddings=True, **kwargs)[0].tolist()
