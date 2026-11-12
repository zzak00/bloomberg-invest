"""Ingest a filing: store the PDF, parse it, record the parse Run, then chunk, embed and extract it,
and link the names its facts write."""

import hashlib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.tokens import TokenCounter
from bloomberg_invest.domain.chunking import Caps
from bloomberg_invest.domain.model import DocumentMeta, RunInfo, RunStatus, RunStep
from bloomberg_invest.service_layer.chunk import Chunked, chunk_document
from bloomberg_invest.service_layer.embed import Embedded, embed_document
from bloomberg_invest.service_layer.extract import Extracted, Extraction, extract_document
from bloomberg_invest.service_layer.facts import ExtractedFacts, FactExtraction, extract_facts
from bloomberg_invest.service_layer.names import Linked, link_names


@dataclass(frozen=True)
class Ingested:
    document_id: str
    chunked: Chunked
    embedded: Embedded
    extracted: Extracted
    facts: ExtractedFacts
    linked: Linked


class IngestFailed(Exception):
    """The parse failed; a failed Run is recorded on the Document."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"parse failed, recorded as a failed run on document {document_id}")
        self.document_id = document_id


def ingest(
    pdf: Path,
    meta: DocumentMeta,
    store: GraphStore,
    files: DocumentFiles,
    parser: Parser,
    count: TokenCounter,
    caps: Caps,
    embedder: Embedder,
    extraction: Extraction,
    fact_extraction: FactExtraction,
) -> Ingested:
    """Parse the filing, then chunk, embed (#21), extract its figures (#22) and its other facts,
    and link the names they write (#24): each step records its own Run."""
    document_id = _parse(pdf, meta, store, files, parser)
    chunked = chunk_document(document_id, store, files, parser, count, caps)
    embedded = embed_document(document_id, store, embedder)
    extracted = extract_document(document_id, store, files, parser, extraction)
    facts = extract_facts(document_id, store, files, parser, fact_extraction)
    linked = link_names(document_id, store)
    return Ingested(document_id, chunked, embedded, extracted, facts, linked)


def _parse(
    pdf: Path, meta: DocumentMeta, store: GraphStore, files: DocumentFiles, parser: Parser
) -> str:
    """Store the PDF by its SHA-256, parse it and record the parse Run; return the Document id."""
    sha256 = hashlib.sha256(pdf.read_bytes()).hexdigest()
    stored = files.pdf_path(sha256)
    if not stored.exists():
        stored.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf, stored)

    started_at = datetime.now(UTC)

    def run_info(
        *,
        status: RunStatus = RunStatus.succeeded,
        error: str | None = None,
        output: str | None = None,
    ) -> RunInfo:
        return RunInfo(
            step=RunStep.parse,
            tool=parser.tool,
            tool_version=parser.tool_version,
            config=parser.config,
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            error=error,
            output=output,
        )

    output = files.parse_output(sha256, started_at, parser.tool)
    try:
        parsed = parser.parse(stored, files.data_dir / output)
    except Exception as error:
        failed = run_info(
            status=RunStatus.failed,
            error=f"{type(error).__name__}: {error}",
            output=output if (files.data_dir / output).exists() else None,
        )
        raise IngestFailed(store.record_failed_parse(meta, failed, sha256)) from error
    return store.record_parse(meta, parsed, run_info(output=output), sha256)
