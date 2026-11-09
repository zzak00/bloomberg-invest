"""Writing an embed Run's vectors, and ending the embed Run that vouched for older ones (#21)."""

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    CURRENT,
    EMBEDDABLE_CHUNKS,
    _create_run,
)
from bloomberg_invest.domain.model import (
    RunInfo,
    RunStatus,
    RunStep,
)


def _record_embeddings(
    tx: ManagedTransaction, document_id: str, vectors: dict[str, list[float]], run: RunInfo
) -> str:
    run_id = _create_run(tx, document_id, run)
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
        f"""
        MATCH (r:Run {{id: $run_id}})-[:PROCESSED]->(d)
        MATCH (n:Run {{step: $step, status: 'succeeded'}})-[:PROCESSED]->(d)
        WHERE n <> r AND {CURRENT}
        SET n.superseded = true
        CREATE (n)-[:SUPERSEDED_BY]->(r)
        """,
        run_id=run_id,
        step=RunStep.embed.value,
    )
