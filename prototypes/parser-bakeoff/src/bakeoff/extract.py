"""Extract figures from a parsed document with an LLM on Azure OpenAI, page by page.

The LLM sees one page at a time: its tables as HTML whose cells carry IDs, and its paragraphs with
IDs. It returns figures that point to a source ID and copy the value as written. It never returns
coordinates and never computes. Python then checks each figure against its source:

- a cell figure is kept when its number equals the cell's number;
- a paragraph figure is kept when its value appears in the paragraph.

Rejected figures are kept in the output, marked, so the report can show what the check caught.

Needs AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY in the environment, or LLM_BASE_URL (and
optionally LLM_API_KEY) for another OpenAI-compatible server. The deployment is then its model name.
"""

import html
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from openai import OpenAI

from bakeoff.line_items import LINE_ITEMS
from bakeoff.score import number
from bakeoff.tables import ParseResult, Table

INSTRUCTIONS = """You extract financial figures from one page of a company's annual financial report.

Return every value on the page whose meaning matches one of the line items below. For each value:
- line_item: one name from the list, nothing else;
- fiscal_year: the fiscal year the value belongs to, e.g. 2025 for "31-déc.-25", "12M 2025" or "Exercice 2025";
- basis_scope: "consolidated" for group (IFRS) statements, "company-only" for the parent company's own (CGNC) accounts;
- breakdown: empty for the plain line item; otherwise a few words saying which part it is (a segment, "IFRS 16 lease liability", "effective rate", "to minority shareholders"...);
- source_id: the id of the table cell or paragraph holding the value;
- value_as_written: the value copied exactly as printed in that cell or paragraph, with its sign;
- unit_scale: the unit as stated on the page, e.g. "MAD millions", "MAD thousands", "%", "MAD".

Rules:
- Copy values, never compute, convert or round them.
- One entry per value: a row with three year columns gives three entries.
- Skip change columns (variation, %) unless the line item itself is a rate.
- Skip values you cannot tie to a line item; do not force a match.

Line items:
"""

SCHEMA = {
    "type": "object",
    "properties": {
        "figures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "line_item": {"type": "string", "enum": list(LINE_ITEMS)},
                    "fiscal_year": {"type": "integer"},
                    "basis_scope": {"type": "string", "enum": ["consolidated", "company-only"]},
                    "breakdown": {"type": "string"},
                    "source_id": {"type": "string"},
                    "value_as_written": {"type": "string"},
                    "unit_scale": {"type": "string"},
                },
                "required": [
                    "line_item",
                    "fiscal_year",
                    "basis_scope",
                    "breakdown",
                    "source_id",
                    "value_as_written",
                    "unit_scale",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["figures"],
    "additionalProperties": False,
}


@dataclass
class Extracted:
    page: int
    line_item: str
    fiscal_year: int
    basis_scope: str
    breakdown: str
    source_id: str
    value_as_written: str
    unit_scale: str
    source_text: str
    verified: bool


def table_html(table: Table, table_id: str) -> str:
    """The table as HTML, each cell carrying an id the LLM returns to cite it."""
    rows: dict[int, list] = {}
    for cell in table.cells:
        rows.setdefault(cell.row, []).append(cell)
    lines = [f'<table id="{table_id}">']
    for row in sorted(rows):
        cells = "".join(
            f'<td id="{table_id}.r{c.row}.c{c.col}"'
            + (f' colspan="{c.col_span}"' if c.col_span > 1 else "")
            + f">{html.escape(c.text)}</td>"
            for c in sorted(rows[row], key=lambda c: c.col)
        )
        lines.append(f"<tr>{cells}</tr>")
    lines.append("</table>")
    return "\n".join(lines)


def page_sources(result: ParseResult, page: int) -> tuple[str, dict[str, str]]:
    """The page as the LLM sees it, and the text behind every id."""
    texts: dict[str, str] = {}
    parts = [f"Page {page}", "", "Paragraphs:"]
    for i, paragraph in enumerate(p for p in result.paragraphs if p.page == page):
        paragraph_id = f"p{page}.{i}"
        texts[paragraph_id] = paragraph.text
        parts.append(f"[{paragraph_id}] {paragraph.text}")
    parts += ["", "Tables:"]
    tables = [t for t in result.tables if page in t.pages]
    for i, table in enumerate(tables):
        table_id = f"t{page}.{i}"
        for cell in table.cells:
            texts[f"{table_id}.r{cell.row}.c{cell.col}"] = cell.text
        parts.append(table_html(table, table_id))
    return "\n".join(parts), texts


def verified(value: str, source: str | None, source_id: str) -> bool:
    if source is None:
        return False
    if source_id.startswith("t"):
        return bool(number(value)) and number(value) == number(source)
    return " ".join(value.split()) in " ".join(source.split())


def client() -> OpenAI:
    """Any OpenAI-compatible server when LLM_BASE_URL is set (vLLM, Ollama...), Azure OpenAI otherwise."""
    if base_url := os.environ.get("LLM_BASE_URL"):
        return OpenAI(base_url=base_url, api_key=os.environ.get("LLM_API_KEY", "none"))
    endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
    return OpenAI(base_url=f"{endpoint}/openai/v1/", api_key=os.environ["AZURE_OPENAI_API_KEY"])


def extract(result: ParseResult, pages: list[int], deployment: str, out: Path) -> list[Extracted]:
    llm = client()
    instructions = INSTRUCTIONS + "\n".join(f"- {name}: {text}" for name, text in LINE_ITEMS.items())
    figures, usage = [], {"input_tokens": 0, "output_tokens": 0}
    started = time.monotonic()
    for page in pages:
        prompt, texts = page_sources(result, page)
        response = llm.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": instructions},
                {"role": "user", "content": prompt},
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "figures", "schema": SCHEMA, "strict": True},
            },
        )
        usage["input_tokens"] += response.usage.prompt_tokens
        usage["output_tokens"] += response.usage.completion_tokens
        for item in json.loads(response.choices[0].message.content)["figures"]:
            source = texts.get(item["source_id"])
            figures.append(
                Extracted(
                    page=page,
                    **item,
                    source_text=source or "",
                    verified=verified(item["value_as_written"], source, item["source_id"]),
                )
            )
        print(f"{deployment} p{page}: {sum(f.page == page for f in figures)} figures")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {
                "deployment": deployment,
                "parser": result.parser,
                "seconds": round(time.monotonic() - started, 1),
                "usage": usage,
                "figures": [asdict(f) for f in figures],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return figures
