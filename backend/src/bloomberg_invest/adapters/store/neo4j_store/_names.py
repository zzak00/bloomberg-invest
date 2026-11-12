"""Linking names to Organisations and Persons (#19 R7): what a link Run resolves, and what a
person decides in CHECKS Names. An Alias resolves through one `ALIAS_OF`, made by the link Run
or by the person's Review it names; a Review is never deleted, a later one takes its place."""

import uuid
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import _create_run, current
from bloomberg_invest.adapters.store.neo4j_store._reads import _document_ref, _passage
from bloomberg_invest.domain.model import RunInfo, RunStatus
from bloomberg_invest.domain.names import AGGREGATE_NAMES, NameReviewDraft, NameVerdict
from bloomberg_invest.views import EntityRef, NameCheck, NameReview, NameSource

# Each aggregate Alias whose company's name resolves gets that company's Aggregate, created on
# first use: one per company and kind (`free_float:<company key>`).
LINK_AGGREGATES = """
MATCH (agg:Alias)
WHERE agg.key CONTAINS ':' AND NOT EXISTS { (agg)-[:ALIAS_OF]->() }
WITH agg, split(agg.key, ':') AS parts
MATCH (:Alias {key: parts[1]})-[:ALIAS_OF]->(company:Organisation)
MERGE (g:Organisation {aggregate: parts[0], aggregate_of: company.id})
  ON CREATE SET g.id = randomUUID(), g.name = $names[parts[0]], g.kind = 'aggregate'
MERGE (g)-[:AGGREGATE_OF]->(company)
CREATE (agg)-[:ALIAS_OF {by: $by}]->(g)
RETURN count(agg) AS linked
"""


def _link_aggregates(tx: ManagedTransaction, by: str) -> int:
    return tx.run(
        LINK_AGGREGATES, by=by, names={k.value: v for k, v in AGGREGATE_NAMES.items()}
    ).single(strict=True)["linked"]


def _record_links(
    tx: ManagedTransaction, document_id: str, links: list[tuple[str, str]], run: RunInfo
) -> tuple[str, int]:
    """Record a link Run: each (Alias key, entity id) links that Alias, then every aggregate
    whose company is now known. Returns the Run id and how many Aliases it linked."""
    run_id = _create_run(tx, document_id, run)
    if run.status != RunStatus.succeeded:
        return run_id, 0
    linked = tx.run(
        """
        UNWIND $links AS link
        MATCH (a:Alias {key: link[0]}) WHERE NOT EXISTS { (a)-[:ALIAS_OF]->() }
        CALL (link) {
            MATCH (e:Organisation {id: link[1]}) RETURN e
            UNION
            MATCH (e:Person {id: link[1]}) RETURN e
        }
        CREATE (a)-[:ALIAS_OF {by: $run_id}]->(e)
        RETURN count(a) AS linked
        """,
        links=[list(link) for link in links],
        run_id=run_id,
    ).single(strict=True)["linked"]
    return run_id, linked + _link_aggregates(tx, run_id)


def _record_name_review(tx: ManagedTransaction, key: str, draft: NameReviewDraft) -> str:
    alias = tx.run("MATCH (a:Alias {key: $key}) RETURN a", key=key).single()
    if alias is None:
        raise LookupError(f"no name {key!r}")
    review_id = str(uuid.uuid4())
    properties = {
        "verdict": draft.verdict.value,
        "reviewer": draft.reviewer,
        "reviewed_at": draft.reviewed_at,
        "entity_id": draft.entity_id,
        "name": draft.name,
        "kind": draft.kind.value if draft.kind else None,
    }
    tx.run(
        """
        MATCH (a:Alias {key: $key})
        CREATE (rv:Review {id: $review_id})-[:REVIEWS]->(a)
        SET rv += $properties
        WITH a
        OPTIONAL MATCH (a)-[old:ALIAS_OF]->()
        DELETE old
        WITH DISTINCT a
        REMOVE a.not_an_entity
        """,
        key=key,
        review_id=review_id,
        properties={k: v for k, v in properties.items() if v is not None},
    )
    # The aggregates of a company's name follow it: they resolve again below once it does.
    tx.run(
        """
        MATCH (agg:Alias)-[old:ALIAS_OF]->()
        WHERE agg.key ENDS WITH ':' + $key
        DELETE old
        """,
        key=key,
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
            id=draft.entity_id,
            key=key,
            review_id=review_id,
        ).single(strict=True)["found"]
        if not found:
            raise LookupError(f"no organisation or person {draft.entity_id}")
    elif draft.verdict == NameVerdict.new:
        label = "Person" if draft.kind and draft.kind.value == "person" else "Organisation"
        tx.run(
            f"""
            MATCH (a:Alias {{key: $key}}), (rv:Review {{id: $review_id}})
            CREATE (e:{label} {{id: $id, name: $name}})
            SET e.kind = CASE WHEN $label = 'Organisation' THEN $kind END
            CREATE (a)-[:ALIAS_OF {{by: $review_id}}]->(e), (e)-[:PRODUCED_BY]->(rv)
            """,
            key=key,
            review_id=review_id,
            id=str(uuid.uuid4()),
            name=draft.name,
            kind=draft.kind.value if draft.kind else None,
            label=label,
        )
    elif draft.verdict == NameVerdict.not_an_entity:
        tx.run("MATCH (a:Alias {key: $key}) SET a.not_an_entity = true", key=key)
    _link_aggregates(tx, review_id)
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


KNOWN = """
CALL () {
    MATCH (e:Organisation) WHERE e.aggregate IS NULL AND e.id IS NOT NULL RETURN e
    UNION
    MATCH (e:Person) RETURN e
}
CALL (e) {
    OPTIONAL MATCH (e)-[:LISTED_AS]->(l:Listing)
    OPTIONAL MATCH (a:Alias)-[:ALIAS_OF]->(e)
    RETURN collect(DISTINCT l.name) + collect(DISTINCT a.name) AS names
}
RETURN e, names ORDER BY e.name, e.id
"""


def _entity(e: Any) -> EntityRef:
    kind = "person" if "Person" in e.labels else e.get("aggregate") or e["kind"]
    return EntityRef(id=e["id"], name=e["name"], kind=kind, isin=e.get("isin"))


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
    if a.get("not_an_entity"):
        status = "not_an_entity"
    elif e is not None:
        status = "resolved"
    else:
        status = "to_check"
    return NameCheck(
        alias=a["key"],
        name=a["name"],
        kind=a["kind"],
        status=status,
        entity=_entity(e) if e is not None else None,
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
