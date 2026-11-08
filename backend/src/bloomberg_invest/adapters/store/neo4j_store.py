"""Neo4j implementation of the graph store (ADR 0003).

Neo4j Community enforces uniqueness only. Required properties are enforced by the domain models,
which every write goes through. Reads never return Superseded nodes (ADR 0002).
"""

import json
import uuid
from typing import Any

from neo4j import Driver, ManagedTransaction

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.indexing import EmbedInput, index_text
from bloomberg_invest.domain.model import (
    DocumentMeta,
    PageInfo,
    ParsedDocument,
    RunInfo,
    RunStatus,
    RunStep,
    SectionNode,
    section_not_on_parsed_page,
)
from bloomberg_invest.views import (
    Box,
    Chunk,
    DocumentDetail,
    DocumentRef,
    DocumentSummary,
    Run,
    Section,
)

CONSTRAINTS = [
    ("Document", "id"),
    ("Document", "sha256"),
    ("Run", "id"),
    ("Organisation", "isin"),
    ("Section", "id"),
    ("Chunk", "id"),
]

CURRENT = "coalesce(n.superseded, false) = false"
# The Document's Chunks an embed Run must cover, bound to `n`; `d` is the Document.
EMBEDDABLE_CHUNKS = f"""
MATCH (n:Chunk)-[:FROM_DOCUMENT]->(d:Document {{id: $document_id}})
WHERE n.index_text IS NOT NULL AND {CURRENT}
"""

# Chunks are the search unit: the vector index reads the vector embedded from a Chunk's index
# text. A superseded Chunk loses both properties, so it leaves the index and vector search needs
# no filter for current Chunks (a filter after SEARCH ... LIMIT could only shorten the results).
VECTOR_INDEX = "chunk_embedding"
INDEXES = [
    # Neo4j quantizes vectors to bits by default; full precision keeps the measured ranking.
    f"""CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (n:Chunk) ON n.embedding
    OPTIONS {{indexConfig: {{`vector.similarity_function`: 'cosine',
                             `vector.quantization.type`: 'NONE'}}}}""",
]
SUPERSEDE = "SET n.superseded = true REMOVE n.index_text, n.embedding"

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
        for index in INDEXES:
            self._driver.execute_query(index)
        self._driver.execute_query("CALL db.awaitIndexes(60)")

    def record_parse(
        self, meta: DocumentMeta, parsed: ParsedDocument, run: RunInfo, sha256: str
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_parse, meta, parsed, run, sha256)

    def record_failed_parse(self, meta: DocumentMeta, run: RunInfo, sha256: str) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_run, meta, run, sha256)[0]

    def record_chunks(self, document_id: str, chunks: list[ChunkDraft], run: RunInfo) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_chunks, document_id, chunks, run)

    def embed_inputs(self, document_id: str) -> list[EmbedInput]:
        records, _, _ = self._driver.execute_query(
            f"""
            {EMBEDDABLE_CHUNKS}
            RETURN n.id AS id, n.index_text AS text ORDER BY n.index
            """,
            document_id=document_id,
        )
        return [EmbedInput(r["id"], r["text"]) for r in records]

    def record_embeddings(
        self, document_id: str, vectors: dict[str, list[float]], run: RunInfo
    ) -> str:
        with self._driver.session() as session:
            return session.execute_write(_record_embeddings, document_id, vectors, run)

    def current_chunk_run(self, document_id: str) -> str | None:
        records, _, _ = self._driver.execute_query(
            f"""
            MATCH (n:Chunk)-[:FROM_DOCUMENT]->(:Document {{id: $id}})
            WHERE {CURRENT}
            MATCH (n)-[:PRODUCED_BY]->(r:Run)
            RETURN DISTINCT r.id AS id
            """,
            id=document_id,
        )
        return records[0]["id"] if records else None

    def search_vector(self, vector: list[float], limit: int) -> list[str]:
        records, _, _ = self._driver.execute_query(
            f"""
            CYPHER 25
            MATCH (n:Chunk)
            SEARCH n IN (VECTOR INDEX {VECTOR_INDEX} FOR $vector LIMIT $limit) SCORE AS score
            RETURN n.id AS id ORDER BY score DESC
            """,
            vector=vector,
            limit=limit,
        )
        return [r["id"] for r in records]

    def chunks(self, chunk_ids: list[str]) -> list[Chunk]:
        records, _, _ = self._driver.execute_query(
            """
            UNWIND range(0, size($ids) - 1) AS i
            MATCH (n:Chunk {id: $ids[i]})-[:FROM_DOCUMENT]->(d:Document)
            MATCH (d)-[:ISSUED_BY]->(o:Organisation)
            OPTIONAL MATCH path = (d)-[:HAS_SECTION*]->(:Section)<-[:IN_SECTION]-(n)
            CALL (n) {
                MATCH (n)-[:ON_PAGE]->(p:Page)
                WITH p ORDER BY p.number
                RETURN collect(p.number) AS pages
            }
            RETURN n, d, o, pages, [s IN coalesce(nodes(path)[1..-1], []) | s.title] AS section_path
            ORDER BY i
            """,
            ids=chunk_ids,
        )
        return [
            Chunk(
                id=r["n"]["id"],
                kind=r["n"]["kind"],
                text=r["n"]["text"],
                pages=r["pages"],
                boxes=_boxes(r["n"]["boxes"]),
                section_path=r["section_path"],
                document=DocumentRef(
                    id=r["d"]["id"],
                    issuer={"isin": r["o"]["isin"], "name": r["o"]["name"]},
                    doc_type=r["d"]["doc_type"],
                    fiscal_year=r["d"]["fiscal_year"],
                ),
            )
            for r in records
        ]

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
    return document_id


def _record_chunks(
    tx: ManagedTransaction, document_id: str, chunks: list[ChunkDraft], run: RunInfo
) -> str:
    run_id = str(uuid.uuid4())
    created = tx.run(
        """
        MATCH (d:Document {id: $document_id})
        CREATE (r:Run {id: $run_id, step: $step, tool: $tool, tool_version: $tool_version,
                       config: $config, started_at: $started_at, finished_at: $finished_at,
                       status: $status, error: $error, output: $output})-[:PROCESSED]->(d)
        RETURN r.id AS id
        """,
        document_id=document_id,
        run_id=run_id,
        **_run_properties(run),
    ).single()
    if created is None:
        raise LookupError(f"no document {document_id}")
    if run.status != RunStatus.succeeded:
        return run_id

    # Only earlier chunk Runs' outputs: the parse's Pages and Sections stay current.
    tx.run(
        f"""
        MATCH (r:Run {{id: $run_id}})-[:PROCESSED]->(d)
        MATCH (n)-[:PRODUCED_BY]->(earlier:Run {{step: $step}})-[:PROCESSED]->(d)
        WHERE earlier <> r AND {CURRENT}
        {SUPERSEDE}
        CREATE (n)-[:SUPERSEDED_BY]->(r)
        """,
        run_id=run_id,
        step=RunStep.chunk.value,
    )
    _supersede_embed_runs(tx, run_id)
    tx.run(
        f"""
        MATCH (d:Document {{id: $document_id}}), (r:Run {{id: $run_id}})
        UNWIND $chunks AS c
        CREATE (k:Chunk {{id: c.id, index: c.index, kind: c.kind, text: c.text,
                          token_count: c.token_count, index_text: c.index_text, boxes: c.boxes}})
        CREATE (k)-[:FROM_DOCUMENT]->(d), (k)-[:PRODUCED_BY]->(r)
        WITH d, r, c, k
        CALL (d, c, k) {{
            MATCH (d)-[:HAS_SECTION*]->(s:Section {{id: c.section_id}})
            CREATE (k)-[:IN_SECTION]->(s)
        }}
        CALL (d, c, k) {{
            MATCH (d)-[:HAS_PAGE]->(n:Page) WHERE n.number IN c.pages AND {CURRENT}
            CREATE (k)-[:ON_PAGE]->(n)
        }}
        CALL (d, c, k) {{
            MATCH (d)-[:HAS_SECTION*]->(s:Section) WHERE s.id IN c.refers_to
            CREATE (k)-[:REFERS_TO]->(s)
        }}
        """,
        document_id=document_id,
        run_id=run_id,
        chunks=[_chunk_row(c) for c in chunks],
    )
    tx.run(
        """
        MATCH (r:Run {id: $run_id})<-[:PRODUCED_BY]-(k:Chunk)
        WITH k ORDER BY k.index
        WITH collect(k) AS chunks
        UNWIND range(0, size(chunks) - 2) AS i
        WITH chunks[i] AS a, chunks[i + 1] AS b
        CREATE (a)-[:NEXT_CHUNK]->(b)
        """,
        run_id=run_id,
    )
    return run_id


def _record_embeddings(
    tx: ManagedTransaction, document_id: str, vectors: dict[str, list[float]], run: RunInfo
) -> str:
    run_id = str(uuid.uuid4())
    created = tx.run(
        """
        MATCH (d:Document {id: $document_id})
        CREATE (r:Run {id: $run_id, step: $step, tool: $tool, tool_version: $tool_version,
                       config: $config, started_at: $started_at, finished_at: $finished_at,
                       status: $status, error: $error, output: $output})-[:PROCESSED]->(d)
        RETURN r.id AS id
        """,
        document_id=document_id,
        run_id=run_id,
        **_run_properties(run),
    ).single()
    if created is None:
        raise LookupError(f"no document {document_id}")
    if run.status != RunStatus.succeeded:
        return run_id

    # An embed Run embeds every current Chunk of its Document, so its PROCESSED link says which
    # Run made each vector: no link per Chunk. Raising rolls the whole transaction back.
    current = tx.run(
        f"""
        {EMBEDDABLE_CHUNKS}
        RETURN collect(n.id) AS ids
        """,
        document_id=document_id,
    ).single(strict=True)["ids"]
    if set(vectors) != set(current):
        stray, missing = len(set(vectors) - set(current)), len(set(current) - set(vectors))
        raise ValueError(
            f"an embed Run covers every current Chunk: {stray} ids are not current Chunks, "
            f"{missing} current ones have no vector"
        )
    tx.run(
        """
        UNWIND $rows AS row
        MATCH (n:Chunk {id: row.id})
        SET n.embedding = row.vector
        """,
        rows=[{"id": chunk_id, "vector": v} for chunk_id, v in vectors.items()],
    )
    _supersede_embed_runs(tx, run_id)
    return run_id


def _supersede_embed_runs(tx: ManagedTransaction, run_id: str) -> None:
    """Supersede the Document's current embed Run by `run_id`, in the same transaction.

    An embed Run vouches for the vectors of every current Chunk. A re-embed replaces them, and a
    re-parse or re-chunk supersedes the Chunks (removing their vectors), so each ends it.
    """
    tx.run(
        """
        MATCH (r:Run {id: $run_id})-[:PROCESSED]->(d)
        MATCH (earlier:Run {step: $step, status: 'succeeded'})-[:PROCESSED]->(d)
        WHERE earlier <> r AND coalesce(earlier.superseded, false) = false
        SET earlier.superseded = true
        CREATE (earlier)-[:SUPERSEDED_BY]->(r)
        """,
        run_id=run_id,
        step=RunStep.embed.value,
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


def _chunk_row(c: ChunkDraft) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "index": c.index,
        "kind": c.kind,
        "text": c.text,
        "token_count": c.token_count,
        "section_id": c.section_id,
        "pages": list(c.pages),
        "refers_to": list(c.refers_to),
        "index_text": index_text(c),
        # Neo4j has no nested lists: each box is five numbers, page, left, top, right, bottom.
        "boxes": [float(v) for p in c.paragraphs for box in p.boxes for v in box],
    }


def _run_properties(run: RunInfo) -> dict[str, Any]:
    return {
        "step": run.step.value,
        "tool": run.tool,
        "tool_version": run.tool_version,
        "config": json.dumps(run.config, sort_keys=True),
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status.value,
        "error": run.error,
        "output": run.output,
    }


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
