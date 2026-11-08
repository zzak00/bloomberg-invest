"""Neo4j implementation of the graph store (ADR 0003).

Neo4j Community enforces uniqueness only. Required properties are enforced by the domain models,
which every write goes through. Reads never return Superseded nodes (ADR 0002).
"""

from neo4j import Driver

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.adapters.store.neo4j_store._chunks import _record_chunks
from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    CURRENT,
    EMBEDDABLE_CHUNKS,
    LATEST_PARSE,
    VECTOR_INDEX,
)
from bloomberg_invest.adapters.store.neo4j_store._embed import _record_embeddings
from bloomberg_invest.adapters.store.neo4j_store._parse import _record_parse, _record_run
from bloomberg_invest.adapters.store.neo4j_store._reads import _boxes, _run, _summary, _tree
from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.indexing import EmbedInput
from bloomberg_invest.domain.model import (
    DocumentMeta,
    PageInfo,
    ParsedDocument,
    RunInfo,
)
from bloomberg_invest.views import (
    Chunk,
    DocumentDetail,
    DocumentRef,
    DocumentSummary,
)

CONSTRAINTS = [
    ("Document", "id"),
    ("Document", "sha256"),
    ("Run", "id"),
    ("Organisation", "isin"),
    ("Section", "id"),
    ("Chunk", "id"),
]


INDEXES = [
    # Neo4j quantizes vectors to bits by default; full precision keeps the measured ranking.
    f"""CREATE VECTOR INDEX {VECTOR_INDEX} IF NOT EXISTS FOR (n:Chunk) ON n.embedding
    OPTIONS {{indexConfig: {{`vector.similarity_function`: 'cosine',
                             `vector.quantization.type`: 'NONE'}}}}""",
]


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
            CALL (n) {
                MATCH (n)-[:ON_PAGE]->(p:Page)
                WITH p ORDER BY p.number
                RETURN collect(p.number) AS pages
            }
            RETURN n, d, o, pages
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
                section_path=r["n"]["section_path"],
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
