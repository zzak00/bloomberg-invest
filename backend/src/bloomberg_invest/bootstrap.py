"""The composition root: the one place that picks and builds the concrete adapters.

Entrypoints ask for dependencies here and never name an implementation. Switching an
implementation is a settings change; adding one is an adapter file plus a registry line.
"""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

from neo4j import GraphDatabase, NotificationDisabledClassification

from bloomberg_invest import config
from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.llm import LLM
from bloomberg_invest.adapters.llm.recording import RecordingLLM, ReplayLLM
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.store.neo4j_store import Neo4jStore
from bloomberg_invest.adapters.tokens import TiktokenCounter, TokenCounter
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.service_layer.extract import Extraction
from bloomberg_invest.settings import Settings


def _docling(settings: Settings) -> Parser:
    # Imported here so the API, which never parses, runs without Docling installed.
    from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser

    return DoclingParser()


PARSERS: dict[str, Callable[[Settings], Parser]] = {"docling": _docling}


def _qwen3() -> Embedder:
    # Imported here so code that never embeds runs without torch installed.
    from bloomberg_invest.adapters.embedding.sentence_transformer import (
        SentenceTransformerEmbedder,
    )

    return SentenceTransformerEmbedder("Qwen/Qwen3-Embedding-0.6B", query_prompt="query")


# Qwen3-Embedding-0.6B: the embedder vector search was measured with in the pipeline notebook
# (ADR 0004).
EMBEDDERS: dict[str, Callable[[], Embedder]] = {"qwen3-0.6b": _qwen3}


def _azure_openai(settings: Settings) -> LLM:
    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", settings.azure_openai_endpoint),
            ("AZURE_OPENAI_API_KEY", settings.azure_openai_api_key),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"extracting figures needs {' and '.join(missing)} in the environment")
    # Imported here so code that never extracts runs without the openai client installed.
    from bloomberg_invest.adapters.llm.azure_openai import AzureOpenAILLM

    return AzureOpenAILLM(
        settings.azure_openai_endpoint, settings.azure_openai_api_key, settings.extract_deployment
    )


# Azure OpenAI: the extractor chosen in #10.
LLMS: dict[str, Callable[[Settings], LLM]] = {"azure-openai": _azure_openai}


@dataclass(frozen=True)
class Deps:
    store: GraphStore
    files: DocumentFiles


@contextmanager
def connect(settings: Settings) -> Iterator[Deps]:
    """Open the graph store, ensure its schema, and close it on exit."""
    driver = GraphDatabase.driver(
        settings.neo4j_uri,
        auth=(settings.neo4j_user, settings.neo4j_password),
        # "Property key does not exist" fires for `superseded` until a re-ingest first sets it.
        notifications_disabled_classifications=[NotificationDisabledClassification.UNRECOGNIZED],
    )
    with driver:
        store = Neo4jStore(driver)
        store.ensure_schema()
        yield Deps(store=store, files=DocumentFiles(settings.data_dir))


def parser(settings: Settings) -> Parser:
    """The parser `settings.parser` names."""
    return _choose(PARSERS, "parser", settings.parser)(settings)


def embedder(settings: Settings) -> Embedder:
    """The embedding model `settings.embedder` names; it loads when this is called."""
    return _choose(EMBEDDERS, "embedder", settings.embedder)()


def llm(settings: Settings) -> LLM:
    """The LLM `settings.llm` names, recording its answers when `LLM_RECORD` is set; with
    `LLM_REPLAY` set, answers come from that recording and nothing is called."""
    if settings.llm_replay:
        return ReplayLLM(settings.llm_replay)
    chosen = _choose(LLMS, "llm", settings.llm)(settings)
    return RecordingLLM(chosen, settings.llm_record) if settings.llm_record else chosen


def label_map() -> LabelMap:
    """The label map in force: extraction asks for its line items, the dossier groups by them."""
    return config.label_map()


def extraction(settings: Settings) -> Extraction:
    """The LLM with the current label map and prompt; fails now if its secrets are missing."""
    return Extraction(
        llm(settings), label_map(), config.extract_prompt(), settings.extract_concurrency
    )


def _choose[F](registry: Mapping[str, F], kind: str, name: str) -> F:
    """The factory registered under `name`; an unknown name fails naming the valid choices."""
    if name not in registry:
        raise ValueError(f"unknown {kind} {name!r}, expected {', '.join(sorted(registry))}")
    return registry[name]


def token_counter() -> TokenCounter:
    """The tokenizer the chunk cap is measured in; `tiktoken` loads only when this is called."""
    return TiktokenCounter()
