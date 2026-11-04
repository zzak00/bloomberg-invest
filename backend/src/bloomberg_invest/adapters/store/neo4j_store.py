"""Neo4j implementation of the graph store (ADR 0003).

Neo4j Community enforces uniqueness only. Required properties are enforced by the domain models,
which every write goes through. Reads never return Superseded nodes (ADR 0002).
"""

import json
import uuid
from typing import Any

from neo4j import Driver, ManagedTransaction

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.model import (
    DocumentMeta,
    PageInfo,
    ParsedDocument,
    RunInfo,
    SectionNode,
    section_not_on_parsed_page,
)
from bloomberg_invest.views import DocumentDetail, DocumentSummary, Run, Section

CONSTRAINTS = [
    ("Document", "id"),
    ("Document", "sha256"),
    ("Run", "id"),
    ("Organisation", "isin"),
    ("Section", "id"),
]

CURRENT = "coalesce(n.superseded, false) = false"

LATEST_PARSE = """
MATCH (r:Run {step: 'parse', status: 'succeeded'})-[:PROCESSED]->(d)
WITH d, o, r ORDER BY r.started_at DESC
WITH d, o, collect(r)[0] AS run
"""


class Neo4jStore(GraphStore):
    def __init__(self, driver: Driver) -> None:
        self._driver = driver

    def ensure_schema(self) -> None:
        for label, prop in CONSTRAINTS:
            self._driver.execute_query(
                f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
                f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE"
            )

    def record_parse(
        self, meta: DocumentMeta, parsed: ParsedDocument, run: RunInfo, sha256: str
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_parse, meta, parsed, run, sha256)

    def record_failed_parse(self, meta: DocumentMeta, run: RunInfo, sha256: str) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_run, meta, run, sha256)[0]

    def list_documents(self) -> list[DocumentSummary]:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (d:Document)-[:ISSUED_BY]->(o:Organisation)
            {LATEST_PARSE}
            CALL (d) {{
                MATCH (d)-[:HAS_PAGE]->(n:Page) WHERE {CURRENT} RETURN count(n) AS pages
            }}
            RETURN d, o, run, pages
            ORDER BY o.name, d.fiscal_year DESC, d.doc_type
            """
        )
        return [_summary(r["d"], r["o"], r["run"], r["pages"]) for r in records]

    def get_document(self, document_id: str) -> DocumentDetail | None:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (d:Document {{id: $id}})-[:ISSUED_BY]->(o:Organisation)
            {LATEST_PARSE}
            CALL (d) {{
                MATCH (d)-[:HAS_PAGE]->(n:Page) WHERE {CURRENT}
                WITH n ORDER BY n.number
                RETURN collect(n {{.number, .width, .height}}) AS pages
            }}
            CALL (d) {{
                MATCH (d)-[:HAS_SECTION*]->(n:Section) WHERE {CURRENT}
                MATCH (parent)-[:HAS_SECTION]->(n)
                WITH n, CASE WHEN parent:Section THEN parent.id END AS parent_id
                ORDER BY n.order
                RETURN collect(n {{.id, .title, .level, .page, .bbox, parent_id: parent_id}})
                    AS sections
            }}
            RETURN d, o, run, pages, sections
            """,
            id=document_id,
        )
        if not records:
            return None
        r = records[0]
        summary = _summary(r["d"], r["o"], r["run"], len(r["pages"]))
        return DocumentDetail(
            **summary.model_dump(),
            sha256=r["d"]["sha256"],
            pages=[PageInfo(**p) for p in r["pages"]],
            sections=_tree(r["sections"]),
            run=_run(r["run"]),
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
        step=run.step,
        tool=run.tool,
        tool_version=run.tool_version,
        config=json.dumps(run.config, sort_keys=True),
        started_at=run.started_at,
        finished_at=run.finished_at,
        status=run.status.value,
        error=run.error,
        output=run.output,
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
        SET n.superseded = true
        CREATE (n)-[:SUPERSEDED_BY]->(r)
        """,
        document_id=document_id,
        run_id=run_id,
    )
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
    return document_id


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
