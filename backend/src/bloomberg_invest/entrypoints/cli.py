"""`bloomberg ingest`: parse and chunk a filing; `bloomberg chunk`: re-chunk an ingested one.

    bloomberg ingest data/inbox/Maroc_Telecom_RFA_2025.pdf --issuer-isin MA0000011488 \
        --issuer-name "Maroc Telecom" --doc-type annual_report --fiscal-year 2025 \
        --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
    bloomberg chunk 3d18e4fa-cfca-4a67-92b4-3d6555da68e6
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from bloomberg_invest import bootstrap
from bloomberg_invest.domain.model import DocType, DocumentMeta, Organisation
from bloomberg_invest.service_layer.chunk import Chunked, ChunkFailed, chunk_document
from bloomberg_invest.service_layer.ingest import IngestFailed, ingest
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import Section


def main(argv: list[str] | None = None) -> int:
    args = _arguments().parse_args(argv)
    if args.command == "chunk":
        return _chunk(args.document_id)
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

    settings = Settings.from_env()
    parser = bootstrap.parser(settings)
    with bootstrap.connect(settings) as deps:
        try:
            ingested = ingest(
                args.pdf,
                meta,
                deps.store,
                deps.files,
                parser,
                bootstrap.token_counter(),
                settings.chunk_cap,
            )
        except (IngestFailed, ChunkFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
        detail = deps.store.get_document(ingested.document_id)
    sections = _count_sections(detail.sections)
    print(
        f"Parsed {detail.page_count} pages, {sections} sections (run {detail.run.id}); "
        f"{_chunks(ingested.chunked)}; document {ingested.document_id}"
    )
    return 0


def _chunk(document_id: str) -> int:
    settings = Settings.from_env()
    parser = bootstrap.parser(settings)
    with bootstrap.connect(settings) as deps:
        try:
            chunked = chunk_document(
                document_id,
                deps.store,
                deps.files,
                parser,
                bootstrap.token_counter(),
                settings.chunk_cap,
            )
        except (LookupError, ValueError, ChunkFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
    print(f"{_chunks(chunked)}; document {document_id}")
    return 0


def _failure(error: Exception) -> str:
    """The error, with what caused it when a step failed and recorded a failed Run."""
    return f"{error}: {error.__cause__!r}" if error.__cause__ else str(error)


def _chunks(chunked: Chunked) -> str:
    return f"{chunked.chunks} chunks (run {chunked.run_id})"


def _count_sections(sections: list[Section]) -> int:
    return sum(1 + _count_sections(s.children) for s in sections)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bloomberg")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = commands.add_parser("ingest", help="parse and chunk a filing into the graph")
    ingest_cmd.add_argument("pdf", type=Path)
    ingest_cmd.add_argument("--issuer-isin", required=True)
    ingest_cmd.add_argument("--issuer-name", required=True)
    ingest_cmd.add_argument("--doc-type", required=True, choices=[t.value for t in DocType])
    ingest_cmd.add_argument("--fiscal-year", required=True, type=int)
    ingest_cmd.add_argument("--source-url")
    chunk_cmd = commands.add_parser("chunk", help="re-chunk an ingested filing from its parse")
    chunk_cmd.add_argument("document_id")
    return parser


if __name__ == "__main__":
    sys.exit(main())
