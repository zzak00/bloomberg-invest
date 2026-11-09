"""Embedding with an open model run locally by sentence-transformers (#21: Qwen3-Embedding-0.6B)."""

from importlib.metadata import version

from bloomberg_invest.adapters.embedding import Embedder

# The window: the chunker keeps every Chunk under it (TABLE_CAP splits long tables), so no
# Chunk's end goes unembedded. Longer windows were too slow on CPU (ADR 0004).
MAX_TOKENS = 2048


class SentenceTransformerEmbedder(Embedder):
    tool = "sentence-transformers"
    max_tokens = MAX_TOKENS

    def __init__(self, name: str, query_prompt: str | None = None, batch_size: int = 16) -> None:
        # Imported here so code that never embeds runs without torch installed.
        from sentence_transformers import SentenceTransformer

        self.name = name
        self.tool_version = version("sentence-transformers")
        self._query_prompt = query_prompt
        self._batch_size = batch_size
        # Float32 wherever it runs: Qwen3 loads in bfloat16 by default, many times slower on CPU,
        # and Chunks embedded on one machine are searched with queries embedded on another.
        import torch

        self._model = SentenceTransformer(name, model_kwargs={"dtype": torch.float32})
        self._model.max_seq_length = MAX_TOKENS

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(texts, batch_size=self._batch_size, normalize_embeddings=True)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        kwargs = {"prompt_name": self._query_prompt} if self._query_prompt else {}
        return self._model.encode([text], normalize_embeddings=True, **kwargs)[0].tolist()
