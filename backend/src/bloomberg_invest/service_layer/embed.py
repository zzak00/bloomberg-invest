"""Embed a chunked Document: a vector per current Chunk from its index text, one embed Run."""

from dataclasses import dataclass
from datetime import UTC, datetime

from bloomberg_invest.adapters.embedding import Embedder
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep


class EmbedFailed(Exception):
    """Embedding failed; a failed embed Run is recorded on the Document."""

    def __init__(self, document_id: str, run_id: str) -> None:
        super().__init__(f"embedding failed, recorded as failed run {run_id} on {document_id}")
        self.document_id = document_id
        self.run_id = run_id


@dataclass(frozen=True)
class Embedded:
    run_id: str
    chunks: int


def embed_document(document_id: str, store: GraphStore, embedder: Embedder) -> Embedded:
    if store.get_document(document_id) is None:
        raise LookupError(f"no document {document_id}")
    inputs = store.embed_inputs(document_id)
    chunk_run = store.current_chunk_run(document_id)
    if not inputs or chunk_run is None:
        raise ValueError(f"no current chunks to embed on {document_id}; chunk it first")

    started_at = datetime.now(UTC)

    def run_info(status: RunStatus = RunStatus.succeeded, error: str | None = None) -> RunInfo:
        return RunInfo(
            step=RunStep.embed,
            tool=embedder.tool,
            tool_version=embedder.tool_version,
            config={"model": embedder.name, "chunk_run": chunk_run},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            error=error,
        )

    ids = [i.chunk_id for i in inputs]
    try:
        vectors = embedder.embed_documents([i.text for i in inputs])
    except Exception as error:
        failed = run_info(RunStatus.failed, f"{type(error).__name__}: {error}")
        raise EmbedFailed(document_id, store.record_embeddings(document_id, {}, failed)) from error
    run_id = store.record_embeddings(document_id, dict(zip(ids, vectors, strict=True)), run_info())
    return Embedded(run_id, len(ids))
