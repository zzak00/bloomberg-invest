"""An issuer's facts of the eight kinds in its dossier (#24 AC3, AC4): one row per kind, parties and
details, showing the value in force (#19 R8), and the fact inspector with a Conflict's sides."""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType

from bloomberg_invest.adapters.store import GraphStore
from bloomberg_invest.domain.facts import (
    NOT_SIGNIFICANT,
    SPECS,
    FactKind,
    RowKey,
    Shown,
    Stated,
    row_key,
    shown,
)
from bloomberg_invest.domain.model import DocType
from bloomberg_invest.domain.review import ReviewDraft, Verdict
from bloomberg_invest.service_layer.checks import Checks, NoReviewer, ReviewRefused
from bloomberg_invest.views import (
    CompanyFacts,
    FactDetail,
    FactRow,
    FactSection,
    FactSide,
    Party,
    RejectedFact,
    Review,
    Sentence,
    StatedFact,
)


@dataclass(frozen=True)
class Section:
    """A dossier section: the kind it lists and the roles the company plays in its rows."""

    key: str
    title: str
    kind: FactKind
    roles: tuple[str, ...]


# The dossier's sections, in its order. Auditors list both mandates and opinions.
SECTIONS = [
    Section("ownership", "Ownership", FactKind.shareholding, ("held",)),
    Section("holdings", "Holdings", FactKind.shareholding, ("holder",)),
    Section("subsidiaries", "Subsidiaries", FactKind.consolidation, ("parent",)),
    Section("board", "Board", FactKind.board_seat, ("company",)),
    Section("auditors", "Auditors", FactKind.audit_mandate, ("company",)),
    Section("auditors", "Auditors", FactKind.auditor_opinion, ("company",)),
    Section("dividends", "Dividends", FactKind.dividend, ("company",)),
    Section("listings", "Listings", FactKind.listing, ("company",)),
    Section(
        "related_parties",
        "Related-party agreements",
        FactKind.related_party_agreement,
        ("company", "counterparty"),
    ),
]


def identity(party: Party) -> str:
    """Who a party is for grouping: what it resolves to, or its name until a person resolves it."""
    return party.resolved.id if party.resolved is not None else f"alias:{party.alias}"


def stated(fact: StatedFact) -> Stated:
    spec = SPECS[fact.kind]
    when = fact.as_of if spec.time == "as_of" else fact.period_end
    return Stated(
        id=fact.id,
        kind=fact.kind,
        parties=tuple((p.role, identity(p)) for p in fact.parties),
        values=MappingProxyType(fact.values),
        scale=fact.scale,
        when=when,
        annual=fact.document.doc_type == DocType.annual_report,
        recorded_at=fact.recorded_at,
        kept=fact.review is not None,
        place=_place(fact),
    )


def _place(fact: StatedFact) -> tuple[float, ...]:
    """Where the fact is read: its page, its first box's top and left, and where its quote
    starts in its paragraph."""
    passage = fact.passage
    box = passage.boxes[0] if passage.boxes else None
    start = passage.text.find(passage.quote) if passage.quote else 0
    return (fact.page, box.top if box else 0.0, box.left if box else 0.0, float(max(start, 0)))


def rows(facts: Sequence[StatedFact]) -> list[tuple[Shown, dict[str, StatedFact]]]:
    """Every row the facts make, with the facts by id."""
    by_id = {f.id: f for f in facts}
    keyed: dict[RowKey, list[Stated]] = defaultdict(list)
    for fact in facts:
        s = stated(fact)
        keyed[row_key(s)].append(s)
    return [(shown(group), by_id) for group in keyed.values()]


def company_facts(isin: str, store: GraphStore) -> CompanyFacts | None:
    """The issuer's facts by section: those of its filings and of any other naming it."""
    if store.issuer(isin) is None:
        return None
    facts, _ = store.facts(isin)
    placed: dict[str, list[FactRow]] = defaultdict(list)
    titles = {}
    placed_keys = set()
    for row, by_id in rows(facts):
        fact = by_id[row.fact.id]
        for section in SECTIONS:
            if fact.kind != section.kind:
                continue
            if any(p.role in section.roles and _is(p, isin) for p in fact.parties):
                placed[section.key].append(_row(row, by_id))
                titles[section.key] = section.title
                placed_keys.add(row_key(row.fact))
                break
    unlinked = sum(
        1
        for f in facts
        if f.document.issuer.isin == isin
        and row_key(stated(f)) not in placed_keys
        and any(p.resolved is None and not p.not_a_party for p in f.parties)
    )
    sections = [
        FactSection(key=key, title=titles[key], rows=sorted(placed[key], key=_order))
        for key in dict.fromkeys(s.key for s in SECTIONS)
        if placed[key]
    ]
    return CompanyFacts(
        count=sum(len(r.sources) + sum(len(g) for g in r.others) for s in sections for r in s.rows),
        sections=sections,
        unlinked=unlinked,
    )


def _is(party: Party, isin: str) -> bool:
    return party.resolved is not None and party.resolved.isin == isin


def _order(row: FactRow) -> tuple:
    """Newest first, then by page: the filing's reading order."""
    when = row.shown.as_of or row.shown.period_end
    return (-when.toordinal(), row.shown.page, row.shown.id)


def _row(row: Shown, by_id: dict[str, StatedFact]) -> FactRow:
    fact = by_id[row.fact.id]
    return FactRow(
        kind=fact.kind,
        shown=fact,
        why=row.why,
        sentence=sentence(fact),
        sources=[by_id[f.id] for f in row.agreeing],
        others=[[by_id[f.id] for f in group] for group in row.others],
        conflict=row.conflict,
        kept_earlier=row.kept_earlier,
    )


def rejected_facts(store: GraphStore, isin: str | None = None) -> list[RejectedFact]:
    """The facts the check refused (D2), of one issuer's filings or every one, by page: kept
    with the reason, never in the dossier."""
    _, rejected = store.facts(isin)
    return sorted(rejected, key=lambda r: (r.document.id, r.page, r.kind, r.id))


def fact_detail(fact_id: str, store: GraphStore) -> FactDetail | None:
    """One fact as the inspector shows it, current or not; with both sides of a Conflict."""
    fact = store.fact(fact_id)
    if not isinstance(fact, StatedFact):
        return None
    key = row_key(stated(fact))
    facts, _ = store.facts()
    same = [f for f in facts if row_key(stated(f)) == key]
    why, sides = None, []
    if any(f.id == fact.id for f in same):
        [(row, by_id)] = rows(same)
        at_date = [row.agreeing, *row.others]
        if any(f.id == fact.id for group in at_date for f in group):
            why = row.why if row.fact.id == fact.id else None
            sides = [
                FactSide(
                    fact=by_id[group[0].id],
                    sentence=sentence(by_id[group[0].id]),
                    sources=len(group),
                    in_use=i == 0,
                )
                for i, group in enumerate(at_date)
            ]
    return FactDetail(**fact.model_dump(), sentence=sentence(fact), why=why, sides=sides)


def record_fact_review(
    fact_id: str,
    verdict: Verdict,
    store: GraphStore,
    checks: Checks,
    now: datetime | None = None,
) -> Review:
    """Keep a value of a Conflict (an accepted Review: it is shown, D5), or undo that."""
    if not checks.reviewer:
        raise NoReviewer()
    fact = store.fact(fact_id)
    if not isinstance(fact, StatedFact) or store.facts(ids=[fact_id])[0] == []:
        raise LookupError("No such current fact: reload the dossier")
    if verdict == Verdict.corrected:
        raise ReviewRefused("A fact's value is kept or reopened, never typed")
    if verdict == Verdict.reopened and fact.review is None:
        raise ReviewRefused("Nobody kept this value: there is nothing to undo")
    draft = ReviewDraft(
        verdict=verdict, reviewer=checks.reviewer, reviewed_at=now or datetime.now(UTC)
    )
    review_id = store.record_review([fact_id], draft)
    return Review(
        id=review_id, verdict=draft.verdict, reviewer=draft.reviewer, reviewed_at=draft.reviewed_at
    )


def _name(fact: StatedFact, role: str) -> str:
    party = next((p for p in fact.parties if p.role == role), None)
    if party is None:
        return ""
    return party.resolved.name if party.resolved is not None else party.name


def _percent(value: object) -> str:
    if value in (None, ""):
        return ""
    # "NS": a stake the filing calls not significant, with no percentage.
    return "a non-significant stake" if str(value).lower() in NOT_SIGNIFICANT else f"{value} %"


def _amount(fact: StatedFact) -> str:
    unit = fact.values.get("unit") or ""
    return f"{fact.values.get('amount')} {unit}".strip()


def _scope(values: Mapping[str, object]) -> str:
    return "consolidated" if values.get("basis_scope") == "consolidated" else "company-only"


BODIES = {
    "board": "board",
    "audit_committee": "audit committee",
    "other_committee": "a board committee",
    "executive": "executive team",
}


def sentence(fact: StatedFact) -> Sentence:
    """The fact in one sentence, as the inspector heads it, its value marked."""
    v, name = fact.values, lambda role: _name(fact, role)
    year = f"FY{fact.fiscal_year}" if fact.fiscal_year else ""
    match fact.kind:
        case FactKind.shareholding:
            held = _percent(v.get("percent")) or f"{v.get('shares')} shares"
            votes = " (voting rights)" if v.get("rights") == "voting" else ""
            return Sentence(
                before=f"{name('holder')} holds ", value=held, after=f" of {name('held')}{votes}"
            )
        case FactKind.board_seat:
            verb = {"serving": "is", "appointed": "was appointed", "left": "left as"}[
                v.get("status") or "serving"
            ]
            return Sentence(
                before=f"{name('member')} {verb} ",
                value=str(v.get("role") or ""),
                after=f" of {name('company')}'s {BODIES[v.get('body') or 'board']}",
            )
        case FactKind.audit_mandate:
            scope = _scope(v)
            return Sentence(
                before="",
                value=name("auditor"),
                after=f" audits {name('company')}'s {scope} accounts for {year}",
            )
        case FactKind.listing:
            return Sentence(
                before=f"{name('company')} is listed on ",
                value=name("exchange"),
                after=f" as {v['ticker']}" if v.get("ticker") else "",
            )
        case FactKind.consolidation:
            share = _percent(v.get("interest") or v.get("control"))
            method = {
                "full": "fully consolidated",
                "equity": "equity-accounted",
                "proportional": "proportionally consolidated",
            }[v.get("method") or "full"]
            return Sentence(
                before=f"{name('parent')} holds ",
                value=share or method,
                after=f" of {name('subsidiary')}, {method}" if share else f": {name('subsidiary')}",
            )
        case FactKind.dividend:
            verb = "proposes" if v.get("status") == "proposed" else "pays"
            per = " per share" if v.get("measure") == "per_share" else " in total"
            return Sentence(
                before=f"{name('company')} {verb} a dividend of ",
                value=_amount(fact),
                after=f"{per} for {year}",
            )
        case FactKind.auditor_opinion:
            scope = _scope(v)
            emphasis = ", with an emphasis of matter" if v.get("emphasis") else ""
            return Sentence(
                before=f"The auditors' opinion on {name('company')}'s {scope} accounts for "
                f"{year} is ",
                value=str(v.get("opinion") or ""),
                after=emphasis,
            )
        case FactKind.related_party_agreement:
            amount = _amount(fact) if v.get("amount") else str(v.get("nature") or "")
            after = f" ({v.get('nature')}, {year})" if v.get("amount") else f" ({year})"
            return Sentence(
                before=f"{name('company')} and {name('counterparty')}: ", value=amount, after=after
            )
