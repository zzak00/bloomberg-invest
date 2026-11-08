"""Turning stored nodes into the read models in `views.py`."""

import json
from typing import Any

from bloomberg_invest.views import (
    Box,
    DocumentSummary,
    Run,
    Section,
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
