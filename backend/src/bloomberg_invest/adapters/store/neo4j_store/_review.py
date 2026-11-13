"""Writing a person's checks (#19 R4, R9): Review nodes, and carrying them over to the figures a
new extract Run reads the same way. A Review is never superseded or deleted; a later one, such as
a reopening, takes its place."""

import uuid
from dataclasses import asdict
from typing import Any

from neo4j import ManagedTransaction

from bloomberg_invest.adapters.store.neo4j_store._cypher import (
    FIGURE_BY_ID,
    LATEST_REVIEW,
    current,
)
from bloomberg_invest.domain.review import Reading, ReviewDraft, Verdict, carried


def _record_review(tx: ManagedTransaction, figure_ids: list[str], draft: ReviewDraft) -> str:
    ids = sorted(set(figure_ids))
    found = tx.run(
        f"""
        UNWIND $ids AS id
        {FIGURE_BY_ID}
        WITH n WHERE {current()}
        RETURN count(n) AS found
        """,
        ids=ids,
    ).single(strict=True)["found"]
    if not ids or found != len(ids):
        raise LookupError("a check needs current figures, and some of these are not")

    review_id = draft.id
    properties = {
        "verdict": draft.verdict.value,
        "reviewer": draft.reviewer,
        "reviewed_at": draft.reviewed_at,
    } | (asdict(draft.correction) if draft.correction else {})
    tx.run(
        f"""
        CREATE (rv:Review {{id: $review_id}})
        SET rv += $properties
        WITH rv
        UNWIND $ids AS id
        {FIGURE_BY_ID}
        CREATE (rv)-[:REVIEWS]->(n)
        """,
        review_id=review_id,
        properties={k: v for k, v in properties.items() if v is not None},
        ids=ids,
    )
    if draft.cell_id is not None:
        cited = tx.run(
            f"""
            MATCH (rv:Review {{id: $review_id}}), (c:Cell {{id: $cell_id}})
            WHERE {current("c")}
            CREATE (rv)-[:CITES]->(c)
            RETURN count(c) AS cited
            """,
            review_id=review_id,
            cell_id=draft.cell_id,
        ).single(strict=True)["cited"]
        if not cited:
            raise LookupError(f"no current cell {draft.cell_id}")
    if draft.quoted is not None:
        quoted = draft.quoted
        cited = tx.run(
            f"""
            MATCH (rv:Review {{id: $review_id}})-[:REVIEWS]->(n)-[:FROM_DOCUMENT]->(d:Document)
            WITH rv, d LIMIT 1
            MATCH (d)-[:HAS_PAGE]->(p:Page {{number: $page}}) WHERE {current("p")}
            CREATE (s:Span:Passage {{id: $span_id, page: $page, quote: $quote, text: $text,
                                     boxes: $boxes, boxes_from: 'quote'}})
            CREATE (rv)-[:CITES]->(s), (s)-[:ON_PAGE]->(p)
            RETURN count(s) AS cited
            """,
            review_id=review_id,
            span_id=str(uuid.uuid4()),
            page=quoted.page,
            quote=quoted.quote,
            text=quoted.text,
            boxes=[float(v) for box in quoted.boxes for v in box],
        ).single(strict=True)["cited"]
        if not cited:
            raise LookupError(f"no current page {quoted.page}")
    return review_id


def _carry_reviews(tx: ManagedTransaction, run_id: str) -> int:
    """Give the new Run's figures the checks of the previous extract Run's figures that read the
    same value from the same source (#19 R4); every other figure goes back to CHECKS. Returns
    how many figures kept a check."""
    previous = tx.run(
        """
        MATCH (r:Run {id: $run_id})-[:PROCESSED]->(d:Document)
        MATCH (earlier:Run {step: 'extract', status: 'succeeded'})-[:PROCESSED]->(d)
        WHERE earlier.started_at < r.started_at
        RETURN earlier.id AS id ORDER BY earlier.started_at DESC LIMIT 1
        """,
        run_id=run_id,
    ).single()
    if previous is None:
        return 0
    checked = [
        (reading, r["rv"]["id"])
        for r in _readings(tx, previous["id"])
        if r["rv"] is not None
        and Verdict(r["rv"]["verdict"]).in_force
        and (reading := _reading(r)) is not None
    ]
    if not checked:
        return 0
    later = [(reading, r["n"]["id"]) for r in _readings(tx, run_id) if (reading := _reading(r))]
    links = carried(checked, later)
    tx.run(
        f"""
        UNWIND $links AS link
        MATCH (rv:Review {{id: link[0]}})
        WITH rv, link[1] AS id
        {FIGURE_BY_ID}
        CREATE (rv)-[:REVIEWS]->(n)
        """,
        links=[list(link) for link in links],
    )
    return len(links)


def _readings(tx: ManagedTransaction, run_id: str) -> list[Any]:
    """Each figure of the Run with where it read its value, and its check in force."""
    return list(
        tx.run(
            f"""
            MATCH (n)-[:PRODUCED_BY]->(:Run {{id: $run_id}})
            WHERE n:Fact OR n:RejectedFigure
            OPTIONAL MATCH (n)-[:CITES]->(c:Cell)<-[:HAS_CELL]-(t:Table)
            OPTIONAL MATCH (n)-[:CITES]->(s:Span)
            {LATEST_REVIEW}
            RETURN n, c {{.page, .row, .col, table: t.index}} AS c, s {{.page, .quote, .text}} AS s,
                   rv {{.id, .verdict}} AS rv
            """,
            run_id=run_id,
        )
    )


def _reading(record: Any) -> Reading | None:
    """What the figure read and where; None for a figure with no Passage, whose check never
    carries over: the page and the id the LLM cited are not the same Cell (#19 R4)."""
    n, cell, span = record["n"], record["c"], record["s"]
    if cell is not None:
        source: tuple[Any, ...] = ("cell", cell["page"], cell["table"], cell["row"], cell["col"])
    elif span is not None:
        source = ("span", span["page"], span["quote"], span["text"])
    else:
        return None
    return Reading(
        line_item=n["line_item"],
        fiscal_year=n["fiscal_year"],
        basis_scope=n.get("basis_scope"),
        breakdown=n["breakdown"],
        value_as_written=n["value_as_written"],
        unit_as_written=n["unit_as_written"],
        source=source,
    )
