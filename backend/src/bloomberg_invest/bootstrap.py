"""The composition root: the one place that picks and builds the concrete adapters.

Entrypoints ask for dependencies here and never name an implementation. Switching an
implementation is a settings change; adding one is an adapter file plus a registry line.
"""

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass

from neo4j import GraphDatabase, NotificationDisabledClassification

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.store.neo4j_store import Neo4jStore
from bloomberg_invest.settings import Settings


def _docling(settings: Settings) -> Parser:
    # Imported here so the API, which never parses, runs without Docling installed.
    from bloomberg_invest.adapters.parsing.docling_parser import DoclingParser

    return DoclingParser()


PARSERS: dict[str, Callable[[Settings], Parser]] = {"docling": _docling}


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
    if settings.parser not in PARSERS:
        expected = ", ".join(sorted(PARSERS))
        raise ValueError(f"unknown parser {settings.parser!r}, expected {expected}")
    return PARSERS[settings.parser](settings)
