"""Writing a chunk Run's Chunks and their links (#21)."""

import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import CURRENT, SUPERSEDE, _run_properties
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
                          token_count: c.token_count, index_text: c.index_text, boxes: c.boxes,
                          section_path: c.section_path}})
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
        # The titles from the top Section down, as the index text's header has them.
        "section_path": list(c.path),
        # Neo4j has no nested lists: each box is five numbers, page, left, top, right, bottom.
        "boxes": [float(v) for p in c.paragraphs for box in p.boxes for v in box],
    }
