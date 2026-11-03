"""`bloomberg ingest`: parse a filing and record it in the graph.

    bloomberg ingest data/inbox/Maroc_Telecom_RFA_2025.pdf --issuer-isin MA0000011488 \
        --issuer-name "Maroc Telecom" --doc-type annual_report --fiscal-year 2025 \
        --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
"""

import argparse
import hashlib
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from bloomberg_invest.domain import (
    DocType,
    DocumentMeta,
    Organisation,
    RunInfo,
    RunStatus,
    SectionNode,
)
from bloomberg_invest.files import DocumentFiles
from bloomberg_invest.parsing import Parser
from bloomberg_invest.settings import Settings
from bloomberg_invest.store import GraphStore
from bloomberg_invest.store.neo4j_store import Neo4jStore


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


def main(argv: list[str] | None = None) -> int:
    args = _arguments().parse_args(argv)
    if args.command != "ingest":
        return 2
    try:
        meta = DocumentMeta(
            issuer=Organisation(isin=args.issuer_isin, name=args.issuer_name),
            doc_type=args.doc_type,
            fiscal_year=args.fiscal_year,
            source_url=args.source_url,
        )
    except ValidationError as error:
        print(error, file=sys.stderr)
        return 2
    if not args.pdf.is_file():
        print(f"No such file: {args.pdf}", file=sys.stderr)
        return 2

    from bloomberg_invest.parsing.docling_parser import DoclingParser

    settings = Settings.from_env()
    with settings.driver() as driver:
        store = Neo4jStore(driver)
        store.ensure_schema()
        try:
            document_id = ingest(
                args.pdf, meta, store, DocumentFiles(settings.data_dir), DoclingParser()
            )
        except IngestFailed as failure:
            print(f"{failure}: {failure.__cause__!r}", file=sys.stderr)
            return 1
        detail = store.get_document(document_id)
    sections = _count_sections(detail.sections)
    print(
        f"Parsed {detail.page_count} pages, {sections} sections "
        f"(run {detail.run.id}), document {document_id}"
    )
    return 0


def _count_sections(sections: list[SectionNode]) -> int:
    return sum(1 + _count_sections(s.children) for s in sections)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bloomberg")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = commands.add_parser("ingest", help="parse a filing and record it in the graph")
    ingest_cmd.add_argument("pdf", type=Path)
    ingest_cmd.add_argument("--issuer-isin", required=True)
    ingest_cmd.add_argument("--issuer-name", required=True)
    ingest_cmd.add_argument("--doc-type", required=True, choices=[t.value for t in DocType])
    ingest_cmd.add_argument("--fiscal-year", required=True, type=int)
    ingest_cmd.add_argument("--source-url")
    return parser


if __name__ == "__main__":
    sys.exit(main())
