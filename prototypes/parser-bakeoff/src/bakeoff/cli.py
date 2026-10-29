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


def parse(parser: str) -> None:
    if parser == "docling":
        from bakeoff.parse_docling import parse as run
    else:
        from bakeoff.parse_azure import parse as run
    result = run(PDF, DATA / "raw" / f"{parser}.json")
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


def main() -> None:
    parser = argparse.ArgumentParser(prog="bakeoff")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("fetch", help="download the golden PDF and check its SHA256")
    parse_command = commands.add_parser(
        "parse", help="run one parser on the golden PDF"
    )
    parse_command.add_argument("parser", choices=["docling", "azure"])
    commands.add_parser(
        "score", help="score every parsed output against the golden figures"
    )
    args = parser.parse_args()
    if args.command == "fetch":
        fetch()
    elif args.command == "parse":
        parse(args.parser)
    else:
        score()
