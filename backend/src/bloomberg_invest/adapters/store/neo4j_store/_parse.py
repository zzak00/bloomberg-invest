"""Writing a parse: the Organisation, Document and Run, then Pages, Sections, Tables and Cells."""

import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import CURRENT, SUPERSEDE, _run_properties
from bloomberg_invest.adapters.store.neo4j_store._embed import _supersede_embed_runs
from bloomberg_invest.domain.model import (
    DocumentMeta,
    ParsedDocument,
    ParsedTable,
    RunInfo,
    SectionNode,
    section_not_on_parsed_page,
)


def _record_run(
    tx: ManagedTransaction, meta: DocumentMeta, run: RunInfo, sha256: str
) -> tuple[str, str]:
    """Merge the Organisation and Document, create the Run; return the Document and Run ids."""
    run_id = str(uuid.uuid4())
    document_id = tx.run(
        """
        MERGE (o:Organisation {isin: $isin})
          ON CREATE SET o.name = $name, o.kind = 'company'
        MERGE (d:Document {sha256: $sha256})
          ON CREATE SET d.id = $new_id
        SET d.doc_type = $doc_type, d.fiscal_year = $fiscal_year,
            d.regulator = $regulator, d.source_url = $source_url
        MERGE (d)-[:ISSUED_BY]->(o)
        CREATE (r:Run {id: $run_id, step: $step, tool: $tool, tool_version: $tool_version,
                       config: $config, started_at: $started_at, finished_at: $finished_at,
                       status: $status, error: $error, output: $output})-[:PROCESSED]->(d)
        // The Document and Organisation link to the Run that created them; later Runs match them.
        CALL (d, o, r) {
            UNWIND [d, o] AS n
            WITH n, r WHERE NOT EXISTS { (n)-[:PRODUCED_BY]->(:Run) }
            CREATE (n)-[:PRODUCED_BY]->(r)
        }
        RETURN d.id AS id
        """,
        isin=meta.issuer.isin,
        name=meta.issuer.name,
        sha256=sha256,
        new_id=str(uuid.uuid4()),
        doc_type=meta.doc_type.value,
        fiscal_year=meta.fiscal_year,
        regulator=meta.regulator,
        source_url=meta.source_url,
        run_id=run_id,
        **_run_properties(run),
    ).single(strict=True)["id"]
    return document_id, run_id


def _record_parse(
    tx: ManagedTransaction, meta: DocumentMeta, parsed: ParsedDocument, run: RunInfo, sha256: str
) -> str:
    document_id, run_id = _record_run(tx, meta, run, sha256)

    # Supersede what earlier Runs produced for this Document before adding the new outputs.
    # The Document and its Organisation are shared by every Run, so they are never superseded.
    tx.run(
        f"""
        MATCH (r:Run {{id: $run_id}})-[:PROCESSED]->(d:Document {{id: $document_id}})
        MATCH (n)-[:PRODUCED_BY]->(earlier:Run)-[:PROCESSED]->(d)
        WHERE earlier <> r AND NOT n:Document AND NOT n:Organisation AND {CURRENT}
        {SUPERSEDE}
        CREATE (n)-[:SUPERSEDED_BY]->(r)
        """,
        document_id=document_id,
        run_id=run_id,
    )
    _supersede_embed_runs(tx, run_id)
    tx.run(
        """
        MATCH (d:Document {id: $document_id}), (r:Run {id: $run_id})
        UNWIND $pages AS page
        CREATE (p:Page {number: page.number, width: page.width, height: page.height})
        CREATE (d)-[:HAS_PAGE]->(p), (p)-[:PRODUCED_BY]->(r)
        """,
        document_id=document_id,
        run_id=run_id,
        pages=[p.model_dump() for p in parsed.pages],
    )
    for row in _flatten(parsed.sections):
        created = tx.run(
            """
            MATCH (d:Document {id: $document_id}), (r:Run {id: $run_id})
            MATCH (d)-[:HAS_PAGE]->(p:Page {number: $s.page})-[:PRODUCED_BY]->(r)
            OPTIONAL MATCH (parent:Section {id: $s.parent_id})
            CREATE (n:Section {id: $s.id, title: $s.title, level: $s.level, page: $s.page,
                               bbox: $s.bbox, order: $s.order})
            CREATE (n)-[:PRODUCED_BY]->(r), (n)-[:ON_PAGE]->(p)
            WITH n, coalesce(parent, d) AS owner
            CREATE (owner)-[:HAS_SECTION]->(n)
            RETURN n.id AS id
            """,
            document_id=document_id,
            run_id=run_id,
            s=row,
        ).single()
        # A MATCH with no Page creates nothing: fail the transaction rather than lose the section.
        if created is None:
            raise ValueError(section_not_on_parsed_page(row["title"], row["page"]))
    _record_tables(tx, document_id, run_id, parsed.tables)
    return document_id


def _record_tables(
    tx: ManagedTransaction, document_id: str, run_id: str, tables: list[ParsedTable]
) -> None:
    """Tables and their Cells, each Cell a Passage a figure can cite (#19 R1, R6)."""
    tx.run(
        """
        MATCH (d:Document {id: $document_id}), (r:Run {id: $run_id})
        UNWIND $tables AS t
        MATCH (d)-[:HAS_PAGE]->(p:Page {number: t.page})-[:PRODUCED_BY]->(r)
        CREATE (table:Table {id: t.id, index: t.index, page: t.page, bbox: t.bbox})
        CREATE (d)-[:HAS_TABLE]->(table), (table)-[:PRODUCED_BY]->(r), (table)-[:ON_PAGE]->(p)
        WITH d, r, table, t
        UNWIND t.cells AS c
        MATCH (d)-[:HAS_PAGE]->(p:Page {number: c.page})-[:PRODUCED_BY]->(r)
        CREATE (n:Cell:Passage {id: c.id, row: c.row, col: c.col, row_span: c.row_span,
                                col_span: c.col_span, text: c.text, page: c.page, bbox: c.bbox,
                                column_header: c.column_header, row_header: c.row_header})
        CREATE (table)-[:HAS_CELL]->(n), (n)-[:PRODUCED_BY]->(r), (n)-[:ON_PAGE]->(p)
        """,
        document_id=document_id,
        run_id=run_id,
        tables=[
            {
                "id": str(uuid.uuid4()),
                "index": i,
                "page": t.page,
                "bbox": list(t.bbox) if t.bbox else None,
                "cells": [
                    c.model_dump() | {"id": str(uuid.uuid4()), "bbox": list(c.bbox)}
                    for c in t.cells
                ],
            }
            for i, t in enumerate(tables)
        ],
    )


def _flatten(nodes: list[SectionNode]) -> list[dict[str, Any]]:
    """Sections in document order, parents before children, each with a new id."""
    rows: list[dict[str, Any]] = []

    def visit(node: SectionNode, parent_id: str | None) -> None:
        row = {
            "id": str(uuid.uuid4()),
            "parent_id": parent_id,
            "order": len(rows),
            "title": node.title,
            "level": node.level,
            "page": node.page,
            "bbox": list(node.bbox) if node.bbox else None,
        }
        rows.append(row)
        for child in node.children:
            visit(child, row["id"])

    for node in nodes:
        visit(node, None)
    return rows
