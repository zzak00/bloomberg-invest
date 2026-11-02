"""bakeoff fetch | parse docling|azure | score"""

import argparse
import hashlib
import sys
import urllib.request
from pathlib import Path

from bakeoff.score import load_golden, report
from bakeoff.tables import ParseResult

HERE = Path(__file__).resolve().parents[2]
DATA = HERE / "data"
GOLDEN = HERE.parents[1] / "golden" / "maroc-telecom-rfa-2025" / "figures.csv"
PDF = DATA / "Maroc_Telecom_RFA_2025.pdf"
PDF_URL = "https://www.ammc.ma/sites/default/files/Maroc_Telecom_RFA_2025.pdf"
PDF_SHA256 = "90e8b73c7f11bfde45d0c7ddb3ce506d162bac2030244d48d9ca2f641ddd4214"


def fetch() -> None:
    DATA.mkdir(exist_ok=True)
    if not PDF.exists():
        # The AMMC site stalls clients without a browser-like User-Agent.
        request = urllib.request.Request(PDF_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            PDF.write_bytes(response.read())
    digest = hashlib.sha256(PDF.read_bytes()).hexdigest()
    if digest != PDF_SHA256:
        sys.exit(f"{PDF} has SHA256 {digest}, expected {PDF_SHA256}")
    print(f"ok: {PDF}")


def golden_pages() -> list[int]:
    return sorted({figure.page for figure in load_golden(GOLDEN)})


def parse(parser: str, pages_per_request: int | None, pages: str | None) -> None:
    raw_out = DATA / "raw" / f"{parser}.json"
    if parser == "paddle":
        from bakeoff.parse_paddle import parse as run

        if pages == "golden":
            selected = golden_pages()
        else:
            selected = [int(n) for n in pages.split(",")] if pages else None
        result = run(PDF, raw_out, selected)
    elif parser.startswith("docling"):
        from bakeoff.parse_docling import parse as run

        result = run(PDF, raw_out, parser)
    else:
        from bakeoff.parse_azure import parse as run

        result = run(PDF, raw_out, pages_per_request)
    result.save(DATA / "parsed" / f"{parser}.json")
    print(
        f"{parser}: {len(result.tables)} tables, {result.page_count} pages, {result.seconds} s"
    )


def score() -> None:
    results = [
        ParseResult.load(path) for path in sorted((DATA / "parsed").glob("*.json"))
    ]
    text = report(results, load_golden(GOLDEN))
    (DATA / "report.md").write_text(text)
    print(text)


def extract(parser: str, deployments: str | None) -> None:
    import os

    from bakeoff.extract import extract as run

    result = ParseResult.load(DATA / "parsed" / f"{parser}.json")
    names = (deployments or os.environ.get("AZURE_OPENAI_DEPLOYMENTS", "")).split(",")
    for deployment in filter(None, (name.strip() for name in names)):
        figures = run(result, golden_pages(), deployment, DATA / "extracted" / f"{deployment.replace('/', '_')}.json")
        rejected = sum(not f.verified for f in figures)
        print(f"{deployment}: {len(figures)} figures, {rejected} rejected by the check")


def score_extract() -> None:
    from bakeoff.extract_score import score as run

    text = run(DATA / "extracted", GOLDEN)
    (DATA / "extract-report.md").write_text(text)
    print(text)


def main() -> None:
    parser = argparse.ArgumentParser(prog="bakeoff")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="download the golden PDF and check its SHA256")
    parse_command = commands.add_parser(
        "parse", help="run one parser on the golden PDF"
    )
    parse_command.add_argument(
        "parser", choices=["docling", "docling-nomatch", "docling-v2", "docling-v2-nomatch", "azure", "paddle"]
    )
    parse_command.add_argument(
        "--pages-per-request",
        type=int,
        help="azure only: send the PDF in slices of this many pages (2 on the free F0 tier)",
    )
    parse_command.add_argument(
        "--pages",
        help="paddle only: comma-separated page numbers, or 'golden' for the pages the golden set cites",
    )
    commands.add_parser(
        "score", help="score every parsed output against the golden figures"
    )
    extract_command = commands.add_parser(
        "extract", help="extract figures from a parsed document with Azure OpenAI, on the golden pages"
    )
    extract_command.add_argument("--parser", default="docling")
    extract_command.add_argument(
        "--deployments", help="comma-separated; defaults to AZURE_OPENAI_DEPLOYMENTS"
    )
    commands.add_parser(
        "score-extract", help="score every extraction against the golden figures"
    )
    args = parser.parse_args()
    if args.command == "fetch":
        fetch()
    elif args.command == "parse":
        parse(args.parser, args.pages_per_request, args.pages)
    elif args.command == "extract":
        extract(args.parser, args.deployments)
    elif args.command == "score-extract":
        score_extract()
    else:
        score()
