"""Writing an embed Run's vectors, and ending the embed Run that vouched for older ones (#21)."""

import uuid

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import EMBEDDABLE_CHUNKS, _run_properties
from bloomberg_invest.domain.model import (
    RunInfo,
    RunStatus,
    RunStep,
)


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
