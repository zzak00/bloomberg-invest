"""Writing a chunk Run's Chunks and their links (#21)."""

import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    CURRENT,
    _create_run,
    _supersede_step,
)
from bloomberg_invest.adapters.store.neo4j_store._embed import _supersede_embed_runs
from bloomberg_invest.domain.chunking import ChunkDraft
from bloomberg_invest.domain.indexing import index_text
from bloomberg_invest.domain.model import (
    RunInfo,
    RunStatus,
    RunStep,
)


def _record_chunks(
    tx: ManagedTransaction, document_id: str, chunks: list[ChunkDraft], run: RunInfo
) -> str:
    run_id = _create_run(tx, document_id, run)
    if run.status != RunStatus.succeeded:
        return run_id

    _supersede_step(tx, run_id, RunStep.chunk.value)
    _supersede_embed_runs(tx, run_id)
    table_ids = {c.table: str(uuid.uuid4()) for c in chunks if c.table is not None}
    tx.run(
        f"""
        MATCH (d:Document {{id: $document_id}}), (r:Run {{id: $run_id}})
        UNWIND $chunks AS c
        CREATE (k:Chunk {{id: c.id, index: c.index, kind: c.kind, text: c.text,
                          token_count: c.token_count, index_text: c.index_text, boxes: c.boxes,
                          section_path: c.section_path, table: c.table, part: c.part,
                          parts: c.parts}})
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
        chunks=[_chunk_row(c, table_ids) for c in chunks],
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


def _chunk_row(c: ChunkDraft, table_ids: dict[int, str]) -> dict[str, Any]:
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
        # The titles from the top Section down, as the index text's header has them.
        "section_path": list(c.path),
        # A table's parts share one id; a text Chunk has none of the three.
        "table": table_ids.get(c.table) if c.table is not None else None,
        "part": c.part or None,
        "parts": c.parts or None,
        # Neo4j has no nested lists: each box is five numbers, page, left, top, right, bottom.
        "boxes": [float(v) for p in c.paragraphs for box in p.boxes for v in box],
    }
