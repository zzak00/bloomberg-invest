"""`bloomberg ingest`: parse a filing and record it in the graph.

    bloomberg ingest data/inbox/Maroc_Telecom_RFA_2025.pdf --issuer-isin MA0000011488 \
        --issuer-name "Maroc Telecom" --doc-type annual_report --fiscal-year 2025 \
        --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from bloomberg_invest import bootstrap
from bloomberg_invest.domain.model import DocType, DocumentMeta, Organisation
from bloomberg_invest.service_layer.ingest import IngestFailed, ingest
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import Section


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

    settings = Settings.from_env()
    parser = bootstrap.parser(settings)
    with bootstrap.connect(settings) as deps:
        try:
            document_id = ingest(args.pdf, meta, deps.store, deps.files, parser)
        except IngestFailed as failure:
            print(f"{failure}: {failure.__cause__!r}", file=sys.stderr)
            return 1
        detail = deps.store.get_document(document_id)
    sections = _count_sections(detail.sections)
    print(
        f"Parsed {detail.page_count} pages, {sections} sections "
        f"(run {detail.run.id}), document {document_id}"
    )
    return 0


def _count_sections(sections: list[Section]) -> int:
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
