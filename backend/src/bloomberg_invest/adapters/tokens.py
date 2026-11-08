"""Token counting for the chunk cap. Implementations import their tokenizer lazily."""

from typing import Protocol


class TokenCounter(Protocol):
    name: str

    def __call__(self, text: str) -> int:
        """The number of tokens in the text."""


class TiktokenCounter(TokenCounter):
    """OpenAI's cl100k_base encoding: a model-neutral proxy until the embedder is chosen (#21)."""

    name = "cl100k_base"

    def __init__(self) -> None:
        import tiktoken

        self._encoding = tiktoken.get_encoding(self.name)

    def __call__(self, text: str) -> int:
        return len(self._encoding.encode(text, disallowed_special=()))
