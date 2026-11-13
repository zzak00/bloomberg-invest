"""KPI values (#27, ADR 0002): computed in Python, kept in the graph with the Facts they read and
the compute Run that wrote them. A recompute writes only the values that changed, and supersedes
the ones they replace, which are kept."""

import json
import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import _run_properties, current
from bloomberg_invest.domain.kpis import KpiChange, KpiResult
from bloomberg_invest.views import KpiTest, KpiUse, StoredKpi

# The KPI values bound to `k`, each with the ids of the Facts it read as `sources`.
WITH_SOURCES = """
OPTIONAL MATCH (k)-[:COMPUTED_FROM]->(f)
WITH k, collect(f.id) AS sources
"""

# An issuer's current KPI values, bound to `k`, with the ids of the Facts each read.
CURRENT_KPIS = f"""
MATCH (k:KpiValue)-[:VALUE_OF]->(:Organisation {{isin: $isin}})
WHERE {current("k")}
{WITH_SOURCES}
"""


def _record_kpi_values(tx: ManagedTransaction, change: KpiChange) -> str:
    """Write a compute Run, a KpiValue per result, and supersede each current value the results
    replace or `gone` names (a KPI and fiscal year no longer computed). Raises LookupError for
    an unknown issuer, or a source that is no current Fact or rejected figure: one superseded
    since it was read, by a re-extract."""
    run_id = str(uuid.uuid4())
    isin, run = change.isin, change.run
    created = tx.run(
        """
        MATCH (o:Organisation {isin: $isin})
        CREATE (r:Run {id: $run_id, step: $step, tool: $tool, tool_version: $tool_version,
                       config: $config, started_at: $started_at, finished_at: $finished_at,
                       status: $status, error: $error, output: $output})-[:PROCESSED]->(o)
        RETURN r.id AS id
        """,
        isin=isin,
        run_id=run_id,
        **_run_properties(run),
    ).single()
    if created is None:
        raise LookupError(f"no issuer {isin}")
    replaced = [[r.kpi, r.fiscal_year] for r in change.results] + [list(g) for g in change.gone]
    tx.run(
        f"""
        MATCH (r:Run {{id: $run_id}})
        UNWIND $replaced AS key
        MATCH (k:KpiValue {{kpi: key[0], fiscal_year: key[1]}})
              -[:VALUE_OF]->(:Organisation {{isin: $isin}})
        WHERE {current("k")}
        SET k.superseded = true
        CREATE (k)-[:SUPERSEDED_BY]->(r)
        """,
        run_id=run_id,
        isin=isin,
        replaced=replaced,
    )
    values = [_properties(r) for r in change.results]
    linked = tx.run(
        f"""
        MATCH (r:Run {{id: $run_id}})-[:PROCESSED]->(o:Organisation)
        UNWIND $values AS v
        CREATE (k:KpiValue {{id: v.id, kpi: v.kpi, fiscal_year: v.fiscal_year, status: v.status,
                            value: v.value, reason: v.reason, out_of: v.out_of,
                            rule_version: $rule_version, rule_sha256: $rule_sha256,
                            label_map: $label_map, computed_at: $computed_at,
                            used: v.used, tests: v.tests}})
        CREATE (k)-[:VALUE_OF]->(o)
        CREATE (k)-[:PRODUCED_BY]->(r)
        WITH k, v
        CALL (k, v) {{
            UNWIND v.sources AS id
            CALL (id) {{
                MATCH (f:Fact {{id: id}}) WHERE {current("f")} RETURN f
                UNION
                MATCH (f:RejectedFigure {{id: id}}) WHERE {current("f")} RETURN f
            }}
            CREATE (k)-[:COMPUTED_FROM]->(f)
            RETURN count(f) AS linked
        }}
        RETURN sum(linked) AS linked
        """,
        run_id=run_id,
        rule_version=change.rule_version,
        rule_sha256=change.rule_sha256,
        label_map=change.label_map,
        computed_at=run.finished_at,
        values=values,
    ).single(strict=True)["linked"]
    sources = sum(len(v["sources"]) for v in values)
    if linked != sources:
        # The transaction rolls back: a value is never kept without every Fact it read.
        raise LookupError(f"{sources - linked} of the KPI values' sources are no current figure")
    return run_id


def _properties(result: KpiResult) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "kpi": result.kpi,
        "fiscal_year": result.fiscal_year,
        "status": result.status.value,
        "value": str(result.value) if result.value is not None else None,
        "reason": result.reason,
        "out_of": result.out_of,
        # Lists of pairs and records: Neo4j properties hold flat lists only.
        "used": json.dumps([[u.name, u.fiscal_year] for u in result.used]),
        "tests": json.dumps([[t.name, t.status.value, t.passed, t.reason] for t in result.tests]),
        "sources": list(result.sources),
    }


def _stored_kpi(k: Any, sources: list[str]) -> StoredKpi:
    return StoredKpi(
        id=k["id"],
        kpi=k["kpi"],
        fiscal_year=k["fiscal_year"],
        status=k["status"],
        value=k["value"],
        reason=k["reason"],
        rule_version=k["rule_version"],
        rule_sha256=k["rule_sha256"],
        label_map=k["label_map"],
        out_of=k.get("out_of"),  # a score's only: Neo4j keeps no null property
        computed_at=k["computed_at"].to_native(),
        used=[KpiUse(name=n, fiscal_year=y) for n, y in json.loads(k["used"])],
        sources=sorted(sources),
        tests=[
            KpiTest(name=n, status=s, passed=p, reason=r) for n, s, p, r in json.loads(k["tests"])
        ],
    )
