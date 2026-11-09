"""Chunk a parsed Document: read the parse's saved output, chunk it, record the chunk Run."""

from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.tokens import TokenCounter
from bloomberg_invest.domain.chunking import Caps, SectionRef, chunk
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep
from bloomberg_invest.views import Section

TOOL = "bloomberg-chunker"


class ChunkFailed(Exception):
    """Chunking failed; a failed chunk Run is recorded on the Document."""

    def __init__(self, document_id: str, run_id: str) -> None:
        super().__init__(f"chunking failed, recorded as failed run {run_id} on {document_id}")
        self.document_id = document_id
        self.run_id = run_id


@dataclass(frozen=True)
class Chunked:
    run_id: str
    chunks: int


def chunk_document(
    document_id: str,
    store: GraphStore,
    files: DocumentFiles,
    parser: Parser,
    count: TokenCounter,
    caps: Caps,
) -> Chunked:
    detail = store.get_document(document_id)
    if detail is None:
        raise LookupError(f"no document {document_id}")
    if detail.run.output is None:
        raise ValueError(f"the parse run {detail.run.id} saved no output to chunk; re-ingest")

    started_at = datetime.now(UTC)

    def run_info(status: RunStatus = RunStatus.succeeded, error: str | None = None) -> RunInfo:
        return RunInfo(
            step=RunStep.chunk,
            tool=TOOL,
            tool_version=version("bloomberg-invest"),
            config={
                "cap": str(caps.text),
                "table_cap": str(caps.table),
                "tokenizer": count.name,
                "parse_run": detail.run.id,
                "parser": f"{parser.tool} {parser.tool_version}",
            },
            started_at=started_at,
            finished_at=datetime.now(UTC),
            status=status,
            error=error,
        )

    try:
        blocks = parser.read_blocks(files.data_dir / detail.run.output)
        drafts = chunk(blocks, list(_section_refs(detail.sections)), caps, count)
    except Exception as error:
        failed = run_info(RunStatus.failed, f"{type(error).__name__}: {error}")
        raise ChunkFailed(document_id, store.record_chunks(document_id, [], failed)) from error
    return Chunked(store.record_chunks(document_id, drafts, run_info()), len(drafts))


def _section_refs(sections: list[Section], parent: str | None = None):
    """Sections in document order, parents before children."""
    for s in sections:
        yield SectionRef(id=s.id, title=s.title, page=s.page, parent=parent)
        yield from _section_refs(s.children, s.id)
