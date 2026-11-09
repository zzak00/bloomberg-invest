"""Cypher fragments and row shapes shared by the store's reads and writes."""

import json
import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.domain.model import (
    RunInfo,
)


def current(var: str = "n") -> str:
    """The node bound to `var` is not Superseded (ADR 0002)."""
    return f"coalesce({var}.superseded, false) = false"


CURRENT = current()


# The Document's Chunks an embed Run must cover, bound to `n`; `d` is the Document.
EMBEDDABLE_CHUNKS = f"""
MATCH (n:Chunk)-[:FROM_DOCUMENT]->(d:Document {{id: $document_id}})
WHERE n.index_text IS NOT NULL AND {CURRENT}
"""


# Chunks are the search unit: the vector index reads the vector embedded from a Chunk's index
# text. A superseded Chunk loses both properties, so it leaves the index and vector search needs
# no filter for current Chunks (a filter after SEARCH ... LIMIT could only shorten the results).
VECTOR_INDEX = "chunk_embedding"


SUPERSEDE = "SET n.superseded = true REMOVE n.index_text, n.embedding"


LATEST_PARSE = """
MATCH (r:Run {step: 'parse', status: 'succeeded'})-[:PROCESSED]->(d)
WITH d, o, r ORDER BY r.started_at DESC
WITH d, o, collect(r)[0] AS run
"""


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


def _create_run(tx: ManagedTransaction, document_id: str, run: RunInfo) -> str:
    """Create a Run that PROCESSED an existing Document; return its id."""
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
    return run_id


def _supersede_step(tx: ManagedTransaction, run_id: str, step: str) -> None:
    """Supersede what earlier Runs of the same step produced for the Document, by `run_id`.

    Only that step's outputs: a chunk Run leaves the parse's Pages and Sections current.
    """
    tx.run(
        f"""
        MATCH (r:Run {{id: $run_id}})-[:PROCESSED]->(d)
        MATCH (n)-[:PRODUCED_BY]->(earlier:Run {{step: $step}})-[:PROCESSED]->(d)
        WHERE earlier <> r AND {CURRENT}
        {SUPERSEDE}
        CREATE (n)-[:SUPERSEDED_BY]->(r)
        """,
        run_id=run_id,
        step=step,
    )
