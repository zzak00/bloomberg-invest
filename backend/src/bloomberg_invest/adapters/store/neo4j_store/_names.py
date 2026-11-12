"""Linking names to Organisations and Persons (#19 R7): what a link Run resolves, and what a
person decides in CHECKS Names. An Alias resolves through its current `ALIAS_OF`, made by the
link Run or by the person's Review it names. A later decision supersedes that link, which is kept
(ADR 0002), and a Review is never deleted: a later one takes its place."""

import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import _create_run, current
from bloomberg_invest.adapters.store.neo4j_store._reads import _document_ref, _passage
from bloomberg_invest.domain.model import RunInfo, RunStatus
from bloomberg_invest.domain.names import (
    AggregateName,
    NameReviewDraft,
    NameVerdict,
    PartyKind,
    name_status,
)
from bloomberg_invest.views import NameCheck, NameReview, NameSource, PartyRef

# The ALIAS_OF bound to `link` is the Alias's current one.
CURRENT_LINK = "coalesce(link.superseded, false) = false"
# The Alias bound to `a` resolves to nothing now.
UNLINKED = f"NOT EXISTS {{ (a)-[link:ALIAS_OF]->() WHERE {CURRENT_LINK} }}"


def _link_aggregates(
    tx: ManagedTransaction, aggregates: list[tuple[AggregateName, str]], by: str
) -> int:
    """Link each aggregate Alias given, with its company's id, to that company's Aggregate,
    created on first use: one per company and kind."""
    return tx.run(
        f"""
        UNWIND $aggregates AS g
        MATCH (a:Alias {{key: g.key}}) WHERE {UNLINKED}
        MATCH (company:Organisation {{id: g.company}})
        MERGE (o:Organisation {{aggregate: g.kind, aggregate_of: company.id}})
          ON CREATE SET o.id = randomUUID(), o.name = g.name, o.kind = 'aggregate'
        MERGE (o)-[:AGGREGATE_OF]->(company)
        CREATE (a)-[:ALIAS_OF {{by: $by}}]->(o)
        RETURN count(a) AS linked
        """,
        aggregates=[
            {"key": g.key, "kind": g.kind.value, "name": g.name, "company": company}
            for g, company in aggregates
        ],
        by=by,
    ).single(strict=True)["linked"]


def _record_links(
    tx: ManagedTransaction,
    document_id: str,
    links: list[tuple[str, str]],
    aggregates: list[tuple[AggregateName, str]],
    run: RunInfo,
) -> tuple[str, int]:
    """Record a link Run: each (Alias key, party id) links that Alias, and each aggregate its
    company's Aggregate. Returns the Run id and how many Aliases it linked."""
    run_id = _create_run(tx, document_id, run)
    if run.status != RunStatus.succeeded:
        return run_id, 0
    linked = tx.run(
        f"""
        UNWIND $links AS given
        MATCH (a:Alias {{key: given[0]}}) WHERE {UNLINKED}
        CALL (given) {{
            MATCH (e:Organisation {{id: given[1]}}) RETURN e
            UNION
            MATCH (e:Person {{id: given[1]}}) RETURN e
        }}
        CREATE (a)-[:ALIAS_OF {{by: $run_id}}]->(e)
        RETURN count(a) AS linked
        """,
        links=[list(link) for link in links],
        run_id=run_id,
    ).single(strict=True)["linked"]
    return run_id, linked + _link_aggregates(tx, aggregates, run_id)


def _record_name_review(
    tx: ManagedTransaction, key: str, draft: NameReviewDraft, aggregates: list[AggregateName]
) -> str:
    alias = tx.run("MATCH (a:Alias {key: $key}) RETURN a", key=key).single()
    if alias is None:
        raise LookupError(f"no name {key!r}")
    review_id = str(uuid.uuid4())
    properties = {
        "verdict": draft.verdict.value,
        "reviewer": draft.reviewer,
        "reviewed_at": draft.reviewed_at,
        "party_id": draft.party_id,
        "name": draft.name,
        "kind": draft.kind.value if draft.kind else None,
    }
    # The decision supersedes the name's link, and its company's aggregates' links: they follow
    # it below once it resolves to an Organisation again.
    tx.run(
        f"""
        MATCH (a:Alias {{key: $key}})
        CREATE (rv:Review {{id: $review_id}})-[:REVIEWS]->(a)
        SET rv += $properties
        REMOVE a.not_a_party
        WITH rv
        MATCH (a:Alias)-[link:ALIAS_OF]->() WHERE a.key IN $keys AND {CURRENT_LINK}
        SET link.superseded = true, link.superseded_by = rv.id
        """,
        key=key,
        keys=[key, *(g.key for g in aggregates)],
        review_id=review_id,
        properties={k: v for k, v in properties.items() if v is not None},
    )
    if draft.verdict == NameVerdict.same_as:
        found = tx.run(
            """
            CALL () {
                MATCH (e:Organisation {id: $id}) WHERE e.aggregate IS NULL RETURN e
                UNION
                MATCH (e:Person {id: $id}) RETURN e
            }
            MATCH (a:Alias {key: $key})
            CREATE (a)-[:ALIAS_OF {by: $review_id}]->(e)
            RETURN count(e) AS found
            """,
            id=draft.party_id,
            key=key,
            review_id=review_id,
        ).single(strict=True)["found"]
        if not found:
            raise LookupError(f"no organisation or person {draft.party_id}")
    elif draft.verdict == NameVerdict.new:
        label = "Person" if draft.kind == PartyKind.person else "Organisation"
        tx.run(
            f"""
            MATCH (a:Alias {{key: $key}}), (rv:Review {{id: $review_id}})
            CREATE (e:{label} {{id: $id, name: $name}})
            SET e.kind = $kind
            CREATE (a)-[:ALIAS_OF {{by: $review_id}}]->(e), (e)-[:PRODUCED_BY]->(rv)
            """,
            key=key,
            review_id=review_id,
            id=str(uuid.uuid4()),
            name=draft.name,
            kind=draft.kind.value if draft.kind and label == "Organisation" else None,
        )
    elif draft.verdict == NameVerdict.not_a_party:
        tx.run("MATCH (a:Alias {key: $key}) SET a.not_a_party = true", key=key)
    company = tx.run(
        f"""
        MATCH (:Alias {{key: $key}})-[link:ALIAS_OF]->(o:Organisation) WHERE {CURRENT_LINK}
        RETURN o.id AS id
        """,
        key=key,
    ).single()
    if company is not None:
        _link_aggregates(tx, [(g, company["id"]) for g in aggregates], review_id)
    return review_id


# The current Facts of the Document bound to `d`, bound to `n`.
CURRENT_FACTS = f"""
MATCH (n:Fact)-[:FROM_DOCUMENT]->(d) WHERE n.kind <> 'financial_figure' AND {current()}
"""


def _known(records: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": r["e"]["id"],
            "name": r["e"]["name"],
            "kind": "person" if "Person" in r["e"].labels else r["e"]["kind"],
            "names": sorted({r["e"]["name"], *r["names"]} - {None}),
        }
        for r in records
    ]


KNOWN = f"""
CALL () {{
    MATCH (e:Organisation) WHERE e.aggregate IS NULL AND e.id IS NOT NULL RETURN e
    UNION
    MATCH (e:Person) RETURN e
}}
CALL (e) {{
    OPTIONAL MATCH (e)-[:LISTED_AS]->(l:Listing)
    OPTIONAL MATCH (a:Alias)-[link:ALIAS_OF]->(e) WHERE {CURRENT_LINK}
    RETURN collect(DISTINCT l.name) + collect(DISTINCT a.name) AS names
}}
RETURN e, names ORDER BY e.name, e.id
"""


def _party_ref(e: Any) -> PartyRef:
    kind = "person" if "Person" in e.labels else e.get("aggregate") or e["kind"]
    return PartyRef(id=e["id"], name=e["name"], kind=kind, isin=e.get("isin"))


def _name_check(r: Any) -> NameCheck:
    a, e, rv = r["a"], r["e"], r["rv"]
    review = None
    if rv is not None and rv["verdict"] != NameVerdict.reopened.value:
        review = NameReview(
            id=rv["id"],
            verdict=rv["verdict"],
            reviewer=rv["reviewer"],
            reviewed_at=rv["reviewed_at"].to_native(),
        )
    return NameCheck(
        alias=a["key"],
        name=a["name"],
        kind=a["kind"],
        status=name_status(e is not None, bool(a.get("not_a_party"))),
        resolved=_party_ref(e) if e is not None else None,
        review=review,
        sources=[
            NameSource(
                fact_id=s["n"]["id"],
                kind=s["n"]["kind"],
                role=s["role"],
                written=s["written"],
                quote=s["n"]["quote"],
                document=_document_ref(s["d"], s["o"]),
                page=s["passage"]["page"],
                passage=_passage(s["passage"]),
            )
            for s in r["sources"]
        ],
    )
