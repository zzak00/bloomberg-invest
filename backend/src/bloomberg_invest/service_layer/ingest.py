"""Ingest a filing: store the PDF, parse it and record the parse Run."""

import hashlib
import shutil
from datetime import UTC, datetime
from pathlib import Path

from bloomberg_invest.adapters.files import DocumentFiles
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.model import DocumentMeta, RunInfo, RunStatus


class IngestFailed(Exception):
    """The parse failed; a failed Run is recorded on the Document."""

    def __init__(self, document_id: str) -> None:
        super().__init__(f"parse failed, recorded as a failed run on document {document_id}")
        self.document_id = document_id


def ingest(
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
            step="parse",
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
