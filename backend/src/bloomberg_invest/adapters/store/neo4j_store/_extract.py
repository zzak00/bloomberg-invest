"""Writing an extract Run's figures: Facts that passed the check, RejectedFigures that did not
(#19 R5, R6). A RejectedFigure never carries the Fact label, so no read of Facts can show one."""

import uuid
from datetime import datetime
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    _create_run,
    _supersede_step,
    current,
)
from bloomberg_invest.domain.extraction import CellPassage, FigureDraft, SpanPassage
from bloomberg_invest.domain.label_map import LabelMap
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep

FINANCIAL_FIGURE = "financial_figure"


def _record_extraction(
    tx: ManagedTransaction,
    document_id: str,
    figures: list[FigureDraft],
    label_map: LabelMap,
    run: RunInfo,
) -> str:
    run_id = _create_run(tx, document_id, run)
    if run.status != RunStatus.succeeded:
        return run_id

    _supersede_step(tx, run_id, RunStep.extract.value)
    rows = [_row(f, label_map, run.finished_at) for f in figures]
    tx.run(
        f"""
        MATCH (d:Document {{id: $document_id}})-[:ISSUED_BY]->(o:Organisation)
        MATCH (r:Run {{id: $run_id}})
        UNWIND $rows AS f
        CREATE (n:$(f.label) {{id: f.id}})
        SET n += f.properties
        CREATE (n)-[:ABOUT]->(o), (n)-[:FROM_DOCUMENT]->(d), (n)-[:PRODUCED_BY]->(r)
        WITH d, r, f, n
        CALL (n, f) {{
            MATCH (c:Cell {{id: f.cell_id}}) WHERE {current("c")}
            CREATE (n)-[:CITES]->(c)
        }}
        CALL (d, r, n, f) {{
            WITH * WHERE f.span IS NOT NULL
            MATCH (d)-[:HAS_PAGE]->(p:Page {{number: f.span.page}}) WHERE {current("p")}
            CREATE (s:Span:Passage {{id: f.span.id, page: f.span.page, quote: f.span.quote,
                                     text: f.span.text, boxes: f.span.boxes}})
            CREATE (n)-[:CITES]->(s), (s)-[:PRODUCED_BY]->(r), (s)-[:ON_PAGE]->(p)
        }}
        """,
        document_id=document_id,
        run_id=run_id,
        rows=rows,
    )
    # Every Fact cites its Passage: a cell gone from the current parse would leave one bare.
    # Raising rolls the whole Run back.
    bare = tx.run(
        """
        MATCH (n:Fact)-[:PRODUCED_BY]->(:Run {id: $run_id})
        WHERE NOT EXISTS { (n)-[:CITES]->(:Passage) }
        RETURN count(n) AS bare
        """,
        run_id=run_id,
    ).single(strict=True)["bare"]
    if bare:
        raise ValueError(f"{bare} figures cite a cell that is not in the current parse")
    return run_id


def _row(figure: FigureDraft, label_map: LabelMap, recorded_at: datetime) -> dict[str, Any]:
    line_item = label_map.items.get(figure.line_item)
    period = figure.period
    properties = {
        "kind": FINANCIAL_FIGURE,
        "line_item": figure.line_item,
        # How label map `version` names and files the line item, as the dossier shows it.
        "line_item_title": line_item.title if line_item else None,
        "statement": line_item.statement if line_item else None,
        "label": figure.label,
        "value": figure.value,
        "value_as_written": figure.value_as_written,
        "unit": figure.unit,
        "scale": figure.scale,
        "currency": figure.currency,
        "unit_as_written": figure.unit_scale,
        "fiscal_year": figure.fiscal_year,
        "period_start": period.start if period else None,
        "period_end": period.end if period else None,
        "as_of": period.as_of if period else None,
        "basis_scope": figure.basis_scope,
        "basis_standard": figure.basis_standard,
        "breakdown": figure.breakdown,
        "page": figure.page,
        "source_id": figure.source_id,
        "recorded_at": recorded_at,
        "reason": figure.rejected.value if figure.rejected else None,
    }
    passage = figure.passage
    return {
        "id": str(uuid.uuid4()),
        "label": "RejectedFigure" if figure.rejected else "Fact",
        "properties": properties,
        "cell_id": passage.cell_id if isinstance(passage, CellPassage) else None,
        "span": {
            "id": str(uuid.uuid4()),
            "page": passage.page,
            "quote": passage.quote,
            "text": passage.text,
            "boxes": [float(v) for box in passage.boxes for v in box],
        }
        if isinstance(passage, SpanPassage)
        else None,
    }
