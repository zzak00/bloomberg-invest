"""Turning stored nodes into the read models in `views.py`."""

import json
from typing import Any

from bloomberg_invest.views import (
    Box,
    DocumentRef,
    DocumentSummary,
    Figure,
    Passage,
    Run,
    Section,
    TablePart,
)


def _boxes(flat: list[float]) -> list[Box]:
    return [
        Box(
            page=int(flat[i]),
            left=flat[i + 1],
            top=flat[i + 2],
            right=flat[i + 3],
            bottom=flat[i + 4],
        )
        for i in range(0, len(flat), 5)
    ]


def _tree(rows: list[dict[str, Any]]) -> list[Section]:
    by_id = {r["id"]: Section(**{k: v for k, v in r.items() if k != "parent_id"}) for r in rows}
    roots: list[Section] = []
    for r in rows:
        node = by_id[r["id"]]
        (by_id[r["parent_id"]].children if r["parent_id"] else roots).append(node)
    return roots


def _run(node: Any) -> Run:
    return Run(
        id=node["id"],
        step=node["step"],
        tool=node["tool"],
        tool_version=node["tool_version"],
        config=json.loads(node["config"]),
        started_at=node["started_at"].to_native(),
        finished_at=node["finished_at"].to_native(),
        status=node["status"],
        error=node.get("error"),
        output=node.get("output"),
    )


def _summary(d: Any, o: Any, run: Any, pages: int) -> DocumentSummary:
    return DocumentSummary(
        id=d["id"],
        issuer={"isin": o["isin"], "name": o["name"]},
        doc_type=d["doc_type"],
        fiscal_year=d["fiscal_year"],
        regulator=d["regulator"],
        source_url=d["source_url"],
        page_count=pages,
        ingested_at=run["finished_at"].to_native(),
    )


def _table_part(node: Any) -> TablePart | None:
    if node.get("table") is None:
        return None
    return TablePart(table_id=node["table"], part=node["part"], parts=node["parts"])


def _document_ref(d: Any, o: Any) -> DocumentRef:
    return DocumentRef(
        id=d["id"],
        issuer={"isin": o["isin"], "name": o["name"]},
        doc_type=d["doc_type"],
        fiscal_year=d["fiscal_year"],
    )


def _figure(n: Any, d: Any, o: Any, passage: Any) -> Figure:
    def day(value: Any):
        return value.to_native() if value is not None else None

    cell = "Cell" in passage.labels
    boxes = [passage["page"], *passage["bbox"]] if cell else passage["boxes"]
    return Figure(
        id=n["id"],
        line_item=n["line_item"],
        line_item_title=n["line_item_title"],
        statement=n["statement"],
        label=n["label"],
        value=n["value"],
        value_as_written=n["value_as_written"],
        unit=n["unit"],
        scale=n["scale"],
        currency=n.get("currency"),
        fiscal_year=n["fiscal_year"],
        period_start=day(n.get("period_start")),
        period_end=day(n.get("period_end")),
        as_of=day(n.get("as_of")),
        basis_scope=n["basis_scope"],
        basis_standard=n["basis_standard"],
        breakdown=n["breakdown"],
        recorded_at=n["recorded_at"].to_native(),
        document=_document_ref(d, o),
        passage=Passage(
            kind="cell" if cell else "span",
            page=passage["page"],
            boxes=_boxes(boxes),
            text=passage["text"],
            quote=None if cell else passage["quote"],
        ),
    )
