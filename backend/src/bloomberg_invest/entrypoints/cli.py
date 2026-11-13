"""`bloomberg ingest`: parse, chunk, embed and extract a filing, figures and other facts. `bloomberg chunk`, `bloomberg
embed` and `bloomberg extract` redo one step for an ingested filing; re-chunking embeds the new
Chunks too. Extracting needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY.

    bloomberg ingest data/inbox/Maroc_Telecom_RFA_2025.pdf --issuer-isin MA0000011488 \
        --issuer-name "Maroc Telecom" --doc-type annual_report --fiscal-year 2025 \
        --source-url https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf
    bloomberg chunk 3d18e4fa-cfca-4a67-92b4-3d6555da68e6
    bloomberg embed 3d18e4fa-cfca-4a67-92b4-3d6555da68e6
    bloomberg extract 3d18e4fa-cfca-4a67-92b4-3d6555da68e6
    bloomberg facts 3d18e4fa-cfca-4a67-92b4-3d6555da68e6

`bloomberg facts` re-extracts the other kinds of fact (#24) and links the names they write.
Each of these recomputes the issuer's KPI values after; `bloomberg kpis [--isin ISIN]` does only
that, for one issuer or every one: after a new KPI rule version (#27).

`bloomberg prices ...` keeps daily closes: see `entrypoints/prices.py`.
"""

import argparse
import sys
from pathlib import Path

from pydantic import ValidationError

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.model import DocType, DocumentMeta, Organisation
from bloomberg_invest.entrypoints import prices
from bloomberg_invest.service_layer.checks import Checks
from bloomberg_invest.service_layer.chunk import Chunked, ChunkFailed, chunk_document
from bloomberg_invest.service_layer.company import issuers
from bloomberg_invest.service_layer.embed import Embedded, EmbedFailed, embed_document
from bloomberg_invest.service_layer.extract import Extracted, ExtractFailed, extract_document
from bloomberg_invest.service_layer.facts import ExtractedFacts, FactsFailed, extract_facts
from bloomberg_invest.service_layer.ingest import IngestFailed, ingest
from bloomberg_invest.service_layer.kpis import Computed, compute_kpis
from bloomberg_invest.service_layer.names import Linked, link_names
from bloomberg_invest.settings import Settings
from bloomberg_invest.views import Section


def main(argv: list[str] | None = None) -> int:
    args = _arguments().parse_args(argv)
    if args.command == "prices":
        return prices.run(args)
    if args.command == "chunk":
        return _chunk(args.document_id)
    if args.command == "embed":
        return _embed(args.document_id)
    if args.command == "extract":
        return _extract(args.document_id)
    if args.command == "facts":
        return _facts(args.document_id)
    if args.command == "kpis":
        return _kpis(args.isin)
    try:
        meta = DocumentMeta(
            issuer=Organisation(isin=args.issuer_isin, name=args.issuer_name),
            doc_type=args.doc_type,
            fiscal_year=args.fiscal_year,
            currency=args.currency,
            source_url=args.source_url,
        )
    except ValidationError as error:
        print(error, file=sys.stderr)
        return 2
    if not args.pdf.is_file():
        print(f"No such file: {args.pdf}", file=sys.stderr)
        return 2

    settings = Settings.from_env()
    try:
        # Before the parse: missing Azure secrets fail now, not minutes later.
        extraction = bootstrap.extraction(settings)
        fact_extraction = bootstrap.fact_extraction(settings)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    parser = bootstrap.parser(settings)
    embedder = bootstrap.embedder(settings)
    with bootstrap.connect(settings) as deps:
        try:
            ingested = ingest(
                args.pdf,
                meta,
                deps.store,
                deps.files,
                parser,
                bootstrap.token_counter(),
                settings.caps,
                embedder,
                extraction,
                fact_extraction,
            )
        except (IngestFailed, ChunkFailed, EmbedFailed, ExtractFailed, FactsFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
        computed = _recompute(meta.issuer.isin, deps.store, bootstrap.checks(settings))
        detail = deps.store.get_document(ingested.document_id)
    sections = _count_sections(detail.sections)
    print(
        f"Parsed {detail.page_count} pages, {sections} sections (run {detail.run.id}); "
        f"{_chunks(ingested.chunked)}; {_embedded(ingested.embedded)}; "
        f"{_extracted(ingested.extracted)}; {_facts_line(ingested.facts, ingested.linked)}; "
        f"{computed or NOT_RECOMPUTED}; document {ingested.document_id}"
    )
    return 0 if computed else 1


def _chunk(document_id: str) -> int:
    """Re-chunk, then embed the new Chunks: a Chunk without a vector is never found."""
    settings = Settings.from_env()
    parser = bootstrap.parser(settings)
    embedder = bootstrap.embedder(settings)
    with bootstrap.connect(settings) as deps:
        try:
            chunked = chunk_document(
                document_id,
                deps.store,
                deps.files,
                parser,
                bootstrap.token_counter(),
                settings.caps,
            )
            embedded = embed_document(document_id, deps.store, embedder)
        except (LookupError, ValueError, ChunkFailed, EmbedFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
    print(f"{_chunks(chunked)}; {_embedded(embedded)}; document {document_id}")
    return 0


def _embed(document_id: str) -> int:
    settings = Settings.from_env()
    embedder = bootstrap.embedder(settings)
    with bootstrap.connect(settings) as deps:
        try:
            embedded = embed_document(document_id, deps.store, embedder)
        except (LookupError, ValueError, EmbedFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
    print(f"{_embedded(embedded)}; document {document_id}")
    return 0


def _extract(document_id: str) -> int:
    settings = Settings.from_env()
    try:
        extraction = bootstrap.extraction(settings)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    parser = bootstrap.parser(settings)
    with bootstrap.connect(settings) as deps:
        try:
            extracted = extract_document(document_id, deps.store, deps.files, parser, extraction)
        except (LookupError, ValueError, ExtractFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
        computed = _recompute(
            _issuer(document_id, deps.store), deps.store, bootstrap.checks(settings)
        )
    print(f"{_extracted(extracted)}; {computed or NOT_RECOMPUTED}; document {document_id}")
    return 0 if computed else 1


def _facts(document_id: str) -> int:
    """Re-extract the filing's facts of the other kinds, then link the names they write."""
    settings = Settings.from_env()
    try:
        extraction = bootstrap.fact_extraction(settings)
    except ValueError as error:
        print(error, file=sys.stderr)
        return 2
    parser = bootstrap.parser(settings)
    with bootstrap.connect(settings) as deps:
        try:
            facts = extract_facts(document_id, deps.store, deps.files, parser, extraction)
            linked = link_names(document_id, deps.store)
        except (LookupError, ValueError, FactsFailed) as failure:
            print(_failure(failure), file=sys.stderr)
            return 1
        # Declared dividends feed the payout ratio.
        computed = _recompute(
            _issuer(document_id, deps.store), deps.store, bootstrap.checks(settings)
        )
    print(f"{_facts_line(facts, linked)}; {computed or NOT_RECOMPUTED}; document {document_id}")
    return 0 if computed else 1


def _kpis(isin: str | None) -> int:
    """Recompute the KPI values of one issuer or every one: after a new rule version."""
    settings = Settings.from_env()
    checks = bootstrap.checks(settings)
    failed = 0
    with bootstrap.connect(settings) as deps:
        for one in [isin] if isin else issuers(deps.store):
            # One issuer's failure leaves the others to compute.
            try:
                computed = _compute(one, deps.store, checks)
            except LookupError as failure:
                print(f"{one}: {_failure(failure)}", file=sys.stderr)
                failed += 1
                continue
            print(f"{one}: {_computed(computed)}")
    return 1 if failed else 0


NOT_RECOMPUTED = "KPI values not recomputed"


def _recompute(isin: str, store: GraphStore, checks: Checks) -> str | None:
    """The KPI recompute that ends an extract, as its output line; None once it has said on
    stderr why it failed. What was extracted is kept either way."""
    try:
        return _computed(_compute(isin, store, checks))
    except LookupError as failure:
        print(
            f"{NOT_RECOMPUTED}: {_failure(failure)}; run `bloomberg kpis --isin {isin}`",
            file=sys.stderr,
        )
        return None


def _compute(isin: str, store: GraphStore, checks: Checks) -> Computed:
    return compute_kpis(isin, store, checks.label_map, checks.rules)


def _issuer(document_id: str, store: GraphStore) -> str:
    document = store.get_document(document_id)
    if document is None:
        raise LookupError(f"no document {document_id}")
    return document.issuer.isin


def _failure(error: Exception) -> str:
    """The error, with what caused it when a step failed and recorded a failed Run."""
    return f"{error}: {error.__cause__!r}" if error.__cause__ else str(error)


def _chunks(chunked: Chunked) -> str:
    return f"{chunked.chunks} chunks (run {chunked.run_id})"


def _embedded(embedded: Embedded) -> str:
    return f"embedded {embedded.chunks} chunks (run {embedded.run_id})"


def _extracted(extracted: Extracted) -> str:
    return (
        f"extracted {extracted.figures} figures from {extracted.pages} pages, "
        f"{extracted.rejected} rejected by the check (run {extracted.run_id})"
    )


def _facts_line(facts: ExtractedFacts, linked: Linked) -> str:
    return (
        f"extracted {facts.facts} other facts from {facts.pages} pages, {facts.rejected} rejected "
        f"by the check (run {facts.run_id}); linked {linked.linked} names, "
        f"{linked.to_check} to check in CHECKS (run {linked.run_id})"
    )


def _computed(computed: Computed) -> str:
    if computed.run_id is None:
        return "KPI values unchanged"
    return (
        f"{computed.written} KPI values written, {computed.superseded} superseded "
        f"(run {computed.run_id})"
    )


def _count_sections(sections: list[Section]) -> int:
    return sum(1 + _count_sections(s.children) for s in sections)


def _arguments() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bloomberg")
    commands = parser.add_subparsers(dest="command", required=True)
    ingest_cmd = commands.add_parser("ingest", help="parse, chunk, embed and extract a filing")
    ingest_cmd.add_argument("pdf", type=Path)
    ingest_cmd.add_argument("--issuer-isin", required=True)
    ingest_cmd.add_argument("--issuer-name", required=True)
    ingest_cmd.add_argument("--doc-type", required=True, choices=[t.value for t in DocType])
    ingest_cmd.add_argument("--fiscal-year", required=True, type=int)
    ingest_cmd.add_argument(
        "--currency", default="MAD", help="the currency of its financial statements (ISO 4217)"
    )
    ingest_cmd.add_argument("--source-url")
    chunk_cmd = commands.add_parser(
        "chunk", help="re-chunk an ingested filing from its parse, then embed it"
    )
    chunk_cmd.add_argument("document_id")
    embed_cmd = commands.add_parser("embed", help="re-embed an ingested filing's chunks")
    embed_cmd.add_argument("document_id")
    extract_cmd = commands.add_parser(
        "extract", help="re-extract an ingested filing's financial figures from its parse"
    )
    extract_cmd.add_argument("document_id")
    facts_cmd = commands.add_parser(
        "facts",
        help="re-extract an ingested filing's other facts from its parse and link their names",
    )
    facts_cmd.add_argument("document_id")
    kpis_cmd = commands.add_parser(
        "kpis", help="recompute the KPI values of one issuer, or of every one"
    )
    kpis_cmd.add_argument("--isin")
    prices.add_arguments(commands)
    return parser


if __name__ == "__main__":
    sys.exit(main())
