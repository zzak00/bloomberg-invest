"""The embedder interface: texts in, unit vectors out. Services never see the model library."""

from typing import Protocol


class Embedder(Protocol):
    name: str  # the model, as recorded on the embed Run
    tool: str
    tool_version: str
    max_tokens: int  # the window: a text's tokens past it are not embedded

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """One unit vector per text, in order."""

    def embed_query(self, text: str) -> list[float]:
        """A unit vector for a search query, comparable with the documents' by dot product."""
