"""Linking the names facts write to Organisations and Persons (#19 R7), and CHECKS Names (S7b):
what no rule could link, and what a person decides it stands for."""

from dataclasses import dataclass
from datetime import UTC, datetime

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.model import RunInfo, RunStep
from bloomberg_invest.domain.names import (
    NameReviewDraft,
    NameStatus,
    NameVerdict,
    PartyKind,
    aggregate_of,
    aggregates_of,
    matches,
    similar,
)
from bloomberg_invest.service_layer.checks import Checks, NoReviewer, ReviewRefused
from bloomberg_invest.views import NameCheck, PartyRef

# The rules a link Run applies, recorded on it (#19 R14).
LINK_RULES = (
    "name key: case, accents, punctuation and legal forms; exactly one Organisation or Person"
)


@dataclass(frozen=True)
class Linked:
    run_id: str
    linked: int  # Aliases this Run linked, aggregates included
    to_check: int  # names left for a person: no Organisation or Person, or several


def link_names(document_id: str, store: GraphStore, now: datetime | None = None) -> Linked:
    """Link each name the filing's current facts write to the one Organisation or Person
    known by it; a name matching none, or several, waits in CHECKS."""
    started_at = now or datetime.now(UTC)
    unlinked = store.unlinked_names(document_id)
    names = [n for n in unlinked if aggregate_of(n.key) is None]
    known = store.known_parties()
    links = []
    for name in names:
        found = matches(name.key, known)
        if len(found) == 1:
            links.append((name.key, found[0].id))
    # A company's free float and treasury shares link once the company's name does.
    held = {n.key: aggregate_of(n.key) for n in unlinked if aggregate_of(n.key) is not None}
    companies = store.resolved_names([company for _, company in held.values()]) | dict(links)
    aggregates = [
        (next(g for g in aggregates_of(company) if g.key == key), companies[company])
        for key, (_, company) in held.items()
        if company in companies
    ]
    run = RunInfo(
        step=RunStep.link,
        tool="bloomberg-invest",
        tool_version="1",
        config={"rules": LINK_RULES},
        started_at=started_at,
        finished_at=datetime.now(UTC),
    )
    run_id, linked = store.record_links(document_id, links, aggregates, run)
    return Linked(run_id, linked, len(names) - len(links))


def name_checks(store: GraphStore) -> list[NameCheck]:
    """CHECKS Names: each name to check first, then those a person resolved, each with the
    Organisations and Persons it most likely means."""
    known = store.known_parties()
    rows = []
    for name in store.names_to_check():
        if aggregate_of(name.alias) is not None:
            continue
        candidates = [
            PartyRef(id=k.id, name=k.name, kind=k.kind)
            for k in similar(name.alias, known)
            if name.resolved is None or k.id != name.resolved.id
        ]
        rows.append(name.model_copy(update={"candidates": candidates}))
    return sorted(rows, key=lambda n: (n.status != NameStatus.to_check, n.name.lower(), n.alias))


def record_name_review(
    key: str,
    verdict: NameVerdict,
    store: GraphStore,
    checks: Checks,
    *,
    party_id: str | None = None,
    name: str | None = None,
    kind: PartyKind | None = None,
    now: datetime | None = None,
) -> str:
    """Record what a name stands for: the same as a known Organisation or Person, a new one, or
    neither.

    Raises NoReviewer without a REVIEWER, ReviewRefused for a decision that does not hold
    together, and LookupError for no such name, Organisation or Person."""
    if not checks.reviewer:
        raise NoReviewer()
    if verdict == NameVerdict.new and name is not None and not name.strip():
        raise ReviewRefused("A new organisation or person needs a name")
    try:
        draft = NameReviewDraft(
            verdict=verdict,
            reviewer=checks.reviewer,
            reviewed_at=now or datetime.now(UTC),
            party_id=party_id if verdict == NameVerdict.same_as else None,
            name=name.strip() if verdict == NameVerdict.new and name else None,
            kind=kind if verdict == NameVerdict.new else None,
        )
    except ValueError as error:
        raise ReviewRefused(str(error).capitalize()) from None
    return store.record_name_review(key, draft, aggregates_of(key))


def parties(store: GraphStore) -> list[PartyRef]:
    """Every Organisation and Person a name can be the same as, by name."""
    return [PartyRef(id=k.id, name=k.name, kind=k.kind) for k in store.known_parties()]
