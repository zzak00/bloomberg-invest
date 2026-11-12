"""Writing and reading the eight other kinds of Fact (#24): Facts that passed the check and
RejectedFacts that did not, each naming its parties through Aliases shared across filings.

An Alias is keyed by the name it stands for, so every filing writing `Itissalat Al-Maghrib`
names the same one, and a person resolves it once (#19 R7). Aliases and their Reviews belong to
the name, not to a Run's reading: they are never superseded.
"""

import uuid
from datetime import date, datetime
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    _create_run,
    _supersede_step,
    current,
)
from bloomberg_invest.adapters.store.neo4j_store._reads import (
    _document_ref,
    _passage,
    _review,
)
from bloomberg_invest.domain.extraction import CellPassage, SpanPassage
from bloomberg_invest.domain.facts import SPECS, FactDraft, FactKind
from bloomberg_invest.domain.model import RunInfo, RunStatus, RunStep
from bloomberg_invest.domain.review import Verdict, carried
from bloomberg_invest.views import Party, PartyRef, RejectedFact, StatedFact

FACT_KINDS = [k.value for k in FactKind]
# The kind's `unit` field is the unit as the LLM read it; a Fact's `unit` is a figure's parsed one.
STORED = {"unit": "unit_as_written"}


def _record_fact_extraction(
    tx: ManagedTransaction, document_id: str, facts: list[FactDraft], run: RunInfo
) -> str:
    run_id = _create_run(tx, document_id, run)
    if run.status != RunStatus.succeeded:
        return run_id

    _supersede_step(tx, run_id, RunStep.extract_facts.value)
    rows = [_row(f, run.finished_at) for f in facts]
    tx.run(
        f"""
        MATCH (d:Document {{id: $document_id}})-[:ISSUED_BY]->(o:Organisation)
        MATCH (r:Run {{id: $run_id}})
        UNWIND $rows AS f
        CREATE (n:$(f.label) {{id: f.id}})
        SET n += f.properties
        CREATE (n)-[:ABOUT]->(o), (n)-[:FROM_DOCUMENT]->(d), (n)-[:PRODUCED_BY]->(r)
        WITH d, r, f, n
        CALL (n, f) {{
            UNWIND f.names AS name
            MERGE (a:Alias {{key: name.key}})
              ON CREATE SET a.name = name.name, a.kind = name.kind
            CREATE (n)-[:NAMES {{role: name.role, written: name.written, name: name.name,
                                 kind: name.kind}}]->(a)
        }}
        CALL (n, f) {{
            MATCH (c:Cell {{id: f.cell_id}}) WHERE {current("c")}
            CREATE (n)-[:CITES]->(c)
        }}
        CALL (d, r, n, f) {{
            WITH * WHERE f.span IS NOT NULL
            MATCH (d)-[:HAS_PAGE]->(p:Page {{number: f.span.page}}) WHERE {current("p")}
            CREATE (s:Span:Passage {{id: f.span.id, page: f.span.page, quote: f.span.quote,
                                     text: f.span.text, boxes: f.span.boxes,
                                     boxes_from: f.span.boxes_from}})
            CREATE (n)-[:CITES]->(s), (s)-[:PRODUCED_BY]->(r), (s)-[:ON_PAGE]->(p)
        }}
        """,
        document_id=document_id,
        run_id=run_id,
        rows=rows,
    )
    bare = tx.run(
        """
        MATCH (n:Fact)-[:PRODUCED_BY]->(:Run {id: $run_id})
        WHERE NOT EXISTS { (n)-[:CITES]->(:Passage) }
        RETURN count(n) AS bare
        """,
        run_id=run_id,
    ).single(strict=True)["bare"]
    if bare:
        raise ValueError(f"{bare} facts cite a cell that is not in the current parse")
    _carry_kept(tx, run_id)
    return run_id


def _row(fact: FactDraft, recorded_at: datetime) -> dict[str, Any]:
    spec = SPECS[fact.kind]
    properties: dict[str, Any] = {
        STORED.get(name, name): value for name, value in fact.values.items()
    }
    properties |= {
        "kind": fact.kind.value,
        "quote": fact.quote,
        "source_id": fact.source_id,  # the id the LLM cited, for tracing an answer back
        "recorded_at": recorded_at,
        "amount_value": fact.amount_value,
        "scale": fact.scale,
        "currency": fact.currency,
    }
    if spec.time == "as_of" and not fact.rejected:
        properties["as_of"] = date.fromisoformat(fact.values["as_of"])
    if fact.period is not None:
        properties["period_start"], properties["period_end"] = fact.period
    if fact.rejected:
        properties |= {"page": fact.page, "reason": fact.rejected.value}
    passage = fact.passage
    return {
        "id": str(uuid.uuid4()),
        "label": "RejectedFact" if fact.rejected else "Fact",
        "properties": {k: v for k, v in properties.items() if v is not None},
        "names": [
            {
                "role": n.role,
                "written": n.written,
                "name": n.name,
                "kind": n.kind.value,
                "key": n.key,
            }
            for n in fact.names
        ],
        "cell_id": passage.cell_id if isinstance(passage, CellPassage) else None,
        "span": {
            "id": str(uuid.uuid4()),
            "page": passage.page,
            "quote": passage.quote,
            "text": passage.text,
            "boxes": [float(v) for box in passage.boxes for v in box],
            "boxes_from": passage.boxes_from,
        }
        if isinstance(passage, SpanPassage)
        else None,
    }


# The parties of the fact bound to `n`, in no order, each with what its Alias resolves to.
PARTIES = """
CALL (n) {
    MATCH (n)-[names:NAMES]->(a:Alias)
    OPTIONAL MATCH (a)-[link:ALIAS_OF]->(e) WHERE coalesce(link.superseded, false) = false
    RETURN collect({role: names.role, written: names.written, name: names.name,
                    alias: a.key, not_a_party: coalesce(a.not_a_party, false),
                    resolved: CASE WHEN e IS NULL THEN null ELSE
                        {id: e.id, name: e.name, isin: e.isin,
                         kind: coalesce(e.aggregate, CASE WHEN e:Person THEN 'person'
                                                          ELSE e.kind END)} END}) AS parties
}
"""

# A Fact or RejectedFact of the eight kinds by its id, bound to `n`.
FACT_BY_ID = """
CALL (id) {
    MATCH (n:Fact {id: id}) RETURN n
    UNION
    MATCH (n:RejectedFact {id: id}) RETURN n
}
"""


def _parties(kind: FactKind, rows: list[dict[str, Any]]) -> list[Party]:
    order = {role: i for i, role in enumerate(SPECS[kind].roles)}
    return [
        Party(
            role=r["role"],
            written=r["written"],
            name=r["name"],
            alias=r["alias"],
            resolved=PartyRef(**r["resolved"]) if r["resolved"] is not None else None,
            not_a_party=r["not_a_party"],
        )
        for r in sorted(rows, key=lambda r: order.get(r["role"], len(order)))
    ]


def _values(kind: FactKind, n: Any) -> dict[str, Any]:
    values = {}
    for f in SPECS[kind].fields:
        value = n.get(STORED.get(f.name, f.name))
        values[f.name] = value.isoformat() if hasattr(value, "isoformat") else value
    return values


def _day(value: Any) -> date | None:
    return value.to_native() if value is not None else None


def _fact_or_rejected(r: Any) -> StatedFact | RejectedFact:
    n, kind = r["n"], FactKind(r["n"]["kind"])
    common = {
        "id": n["id"],
        "kind": kind,
        "parties": _parties(kind, r["parties"]),
        "values": _values(kind, n),
        "quote": n["quote"],
        "recorded_at": n["recorded_at"].to_native(),
        "document": _document_ref(r["d"], r["o"]),
    }
    passage = _passage(r["passage"]) if r["passage"] is not None else None
    if "RejectedFact" in n.labels:
        return RejectedFact(**common, page=n["page"], reason=n["reason"], passage=passage)
    return StatedFact(
        **common,
        amount_value=n.get("amount_value"),
        scale=n.get("scale"),
        currency=n.get("currency"),
        as_of=_day(n.get("as_of")),
        fiscal_year=n.get("fiscal_year"),
        period_start=_day(n.get("period_start")),
        period_end=_day(n.get("period_end")),
        passage=passage,
        page=r["passage"]["page"],
        review=_review(r["rv"], r["rp"]),
    )


def _carry_kept(tx: ManagedTransaction, run_id: str) -> int:
    """Give the new Run's facts the Reviews of the previous facts Run's that read the same
    thing from the same source (#19 R4): a value kept stays kept after a re-run."""
    previous = tx.run(
        """
        MATCH (r:Run {id: $run_id})-[:PROCESSED]->(d:Document)
        MATCH (earlier:Run {step: $step, status: 'succeeded'})-[:PROCESSED]->(d)
        WHERE earlier.started_at < r.started_at
        RETURN earlier.id AS id ORDER BY earlier.started_at DESC LIMIT 1
        """,
        run_id=run_id,
        step=RunStep.extract_facts.value,
    ).single()
    if previous is None:
        return 0
    checked = [
        (reading, r["rv"]["id"])
        for r in _readings(tx, previous["id"])
        if r["rv"] is not None and Verdict(r["rv"]["verdict"]).in_force
        for reading in [_reading(r)]
        if reading is not None
    ]
    if not checked:
        return 0
    later = [(reading, r["n"]["id"]) for r in _readings(tx, run_id) if (reading := _reading(r))]
    links = carried(checked, later)
    tx.run(
        """
        UNWIND $links AS link
        MATCH (rv:Review {id: link[0]}), (n:Fact {id: link[1]})
        CREATE (rv)-[:REVIEWS]->(n)
        """,
        links=[list(link) for link in links],
    )
    return len(links)


def _readings(tx: ManagedTransaction, run_id: str) -> list[Any]:
    return list(
        tx.run(
            """
            MATCH (n:Fact)-[:PRODUCED_BY]->(:Run {id: $run_id})
            OPTIONAL MATCH (n)-[:CITES]->(c:Cell)<-[:HAS_CELL]-(t:Table)
            OPTIONAL MATCH (n)-[:CITES]->(s:Span)
            CALL (n) {
                MATCH (n)-[names:NAMES]->(a:Alias)
                WITH names, a ORDER BY names.role
                RETURN collect([names.role, a.key]) AS names
            }
            OPTIONAL CALL (n) {
                MATCH (rv:Review)-[:REVIEWS]->(n)
                RETURN rv ORDER BY rv.reviewed_at DESC LIMIT 1
            }
            RETURN n, names, c {.page, .row, .col, table: t.index} AS c,
                   s {.page, .quote, .text} AS s, rv {.id, .verdict} AS rv
            """,
            run_id=run_id,
        )
    )


def _reading(record: Any) -> Any:
    """What the fact read and where, as a hashable tuple; None without a Passage."""
    n, cell, span = record["n"], record["c"], record["s"]
    if cell is not None:
        source: tuple[Any, ...] = ("cell", cell["page"], cell["table"], cell["row"], cell["col"])
    elif span is not None:
        source = ("span", span["page"], span["quote"], span["text"])
    else:
        return None
    kind = FactKind(n["kind"])
    values = tuple(sorted((k, str(v)) for k, v in _values(kind, n).items()))
    return (kind.value, tuple(tuple(x) for x in record["names"]), values, source)
