"""The store's side of facts stated in words (#24 AC1, AC2): Facts naming their parties through
Aliases shared by every filing, linking those names, and what a person decides in CHECKS Names.
Run on every GraphStore implementation (the `store` fixture)."""

from datetime import UTC, datetime

import pytest
from conftest import make_run

from bloomberg_invest.domain.extraction import SourceParagraph, page_sources
from bloomberg_invest.domain.facts import FactKind, drafts
from bloomberg_invest.domain.model import DocType, DocumentMeta, Organisation, RunStep
from bloomberg_invest.domain.names import NameReviewDraft, NameVerdict, PartyKind, aggregates_of
from bloomberg_invest.domain.review import ReviewDraft, Verdict

ISIN = "MA0000011488"
OTHER_ISIN = "MA0000099999"
OWNERS = SourceParagraph(
    3,
    "Au 31 décembre 2025, le capital est réparti comme suit : - Société Alpha : 53% ; "
    "- Itissalat Al-Maghrib : 2% ; - Autres : 45%.",
    ((3, 50.0, 300.0, 540.0, 330.0),),
)


def party(written: str, name: str | None = None, kind: str = "company") -> dict:
    return {"written": written, "name": name or written, "kind": kind}


def holding(holder: dict, percent: str, quote: str, held: dict | None = None) -> dict:
    return {
        "holder": holder,
        "held": held or party("Maroc Telecom"),
        "percent": percent,
        "shares": None,
        "rights": "capital",
        "as_of": "2025-12-31",
        "source_id": "p3.0",
        "quote": quote,
    }


ANSWER = [
    holding(party("Société Alpha"), "53", "Société Alpha : 53%"),
    holding(party("Itissalat Al-Maghrib"), "2", "Itissalat Al-Maghrib : 2%"),
    holding(party("Autres", "Free float", "free_float"), "45", "Autres : 45%"),
    # Misread: the page says 53 %.
    holding(party("Société Alpha"), "55", "Société Alpha : 53%"),
]


def run(step: RunStep, minute: int):
    return make_run(minute).model_copy(update={"step": step, "output": None})


def extract_facts(store, document_id: str, answer=ANSWER, minute: int = 20) -> str:
    sources = page_sources(3, [OWNERS], [])
    response = {k.value: answer if k == FactKind.shareholding else [] for k in FactKind}
    return store.record_fact_extraction(
        document_id, drafts(response, sources), run(RunStep.extract_facts, minute)
    )


def name_review(verdict: NameVerdict, minute: int = 40, **fields) -> NameReviewDraft:
    return NameReviewDraft(
        verdict=verdict,
        reviewer="Z. Bajjou",
        reviewed_at=datetime(2026, 11, 12, 9, minute, tzinfo=UTC),
        **fields,
    )


def issuer_id(store, isin: str = ISIN) -> str:
    return next(e.id for e in store.known_parties() if e.name == "Maroc Telecom")


def link_issuer(store, document_id: str) -> None:
    """Link the issuer's own name, as the link Run would."""
    issuer = issuer_id(store)
    free_float = aggregates_of("maroc telecom")[0]
    store.record_links(
        document_id, [("maroc telecom", issuer)], [(free_float, issuer)], run(RunStep.link, 30)
    )


@pytest.fixture
def extracted(store, document):
    document_id, _ = document
    extract_facts(store, document_id)
    return document_id


def other_filing(store, parsed) -> str:
    meta = DocumentMeta(
        issuer=Organisation(isin=OTHER_ISIN, name="Société Alpha"),
        doc_type=DocType.annual_report,
        fiscal_year=2025,
    )
    return store.record_parse(meta, parsed, make_run(1), "f" * 64)


def test_facts_cite_their_passage_and_name_their_parties(store, extracted):
    facts, rejected = store.facts()
    assert len(facts) == 3
    alpha = next(f for f in facts if f.values["percent"] == "53")
    assert alpha.kind == FactKind.shareholding
    assert (alpha.passage.kind, alpha.passage.quote, alpha.page) == (
        "span",
        "Société Alpha : 53%",
        3,
    )
    assert alpha.as_of.isoformat() == "2025-12-31"
    assert [(p.role, p.written, p.alias, p.resolved) for p in alpha.parties] == [
        ("holder", "Société Alpha", "societe alpha", None),
        ("held", "Maroc Telecom", "maroc telecom", None),
    ]
    [misread] = rejected
    assert (misread.reason, misread.values["percent"], misread.page) == (
        "a number it states is not in its quote",
        "55",
        3,
    )


def test_one_name_written_by_two_filings_is_one_alias(store, extracted, parsed, driver):
    extract_facts(store, other_filing(store, parsed))
    records, _, _ = driver.execute_query(
        "MATCH (a:Alias {key: 'societe alpha'})<-[:NAMES]-(n:Fact) RETURN count(DISTINCT a) AS "
        "aliases, count(n) AS facts"
    )
    assert (records[0]["aliases"], records[0]["facts"]) == (1, 2)


def test_linking_resolves_a_name_and_the_free_float_of_its_company(store, extracted):
    assert [n.key for n in store.unlinked_names(extracted)] == [
        "free_float:maroc telecom",
        "itissalat al maghrib",
        "maroc telecom",
        "societe alpha",
    ]
    link_issuer(store, extracted)
    assert [n.key for n in store.unlinked_names(extracted)] == [
        "itissalat al maghrib",
        "societe alpha",
    ]
    facts, _ = store.facts(ISIN)
    free_float = next(f for f in facts if f.values["percent"] == "45")
    holder, held = free_float.parties
    assert (holder.resolved.name, holder.resolved.kind) == ("Free float", PartyKind.free_float)
    assert held.resolved.isin == ISIN
    # One Aggregate per company, however many filings write "Autres".
    link_issuer(store, extracted)
    assert [e.name for e in store.known_parties()] == ["Maroc Telecom"]


def test_a_company_dossier_has_the_facts_naming_it_from_any_filing(store, extracted, parsed):
    other = other_filing(store, parsed)
    extract_facts(store, other)
    alpha = next(e.id for e in store.known_parties() if e.name == "Société Alpha")
    store.record_links(other, [("societe alpha", alpha)], [], run(RunStep.link, 30))
    facts, _ = store.facts(OTHER_ISIN)
    # Its own filing's three, and Maroc Telecom's filing naming it as a holder.
    assert len(facts) == 4


def test_names_no_rule_linked_go_to_checks(store, extracted):
    link_issuer(store, extracted)
    names = [n for n in store.names_to_check() if ":" not in n.alias]
    assert [(n.alias, n.status) for n in names] == [
        ("itissalat al maghrib", "to_check"),
        ("societe alpha", "to_check"),
    ]
    [source] = names[0].sources
    assert (source.written, source.page, source.passage.quote) == (
        "Itissalat Al-Maghrib",
        3,
        "Itissalat Al-Maghrib : 2%",
    )


def test_same_as_resolves_a_name_for_every_filing_writing_it(store, extracted):
    link_issuer(store, extracted)
    store.record_name_review(
        "itissalat al maghrib",
        name_review(NameVerdict.same_as, party_id=issuer_id(store)),
        aggregates_of("itissalat al maghrib"),
    )
    [name] = [n for n in store.names_to_check() if n.alias == "itissalat al maghrib"]
    assert (name.status, name.resolved.isin, name.review.verdict) == (
        "resolved",
        ISIN,
        NameVerdict.same_as,
    )
    # The issuer is now known by that name too.
    known = {e.name: e.names for e in store.known_parties()}
    assert known["Maroc Telecom"] == ["Itissalat Al-Maghrib", "Maroc Telecom"]


def test_new_creates_the_organisation_or_person_the_name_stands_for(store, extracted):
    store.record_name_review(
        "societe alpha",
        name_review(NameVerdict.new, name="Société Alpha", kind=PartyKind.holding),
        [],
    )
    facts, _ = store.facts()
    alpha = next(f for f in facts if f.values["percent"] == "53")
    assert (alpha.parties[0].resolved.name, alpha.parties[0].resolved.kind) == (
        "Société Alpha",
        PartyKind.holding,
    )


def test_not_a_party_and_reopening(store, extracted):
    store.record_name_review("societe alpha", name_review(NameVerdict.not_a_party), [])
    [name] = [n for n in store.names_to_check() if n.alias == "societe alpha"]
    assert (name.status, name.resolved) == ("not_a_party", None)
    assert "societe alpha" not in [n.key for n in store.unlinked_names(extracted)]
    store.record_name_review("societe alpha", name_review(NameVerdict.reopened, minute=50), [])
    [name] = [n for n in store.names_to_check() if n.alias == "societe alpha"]
    assert (name.status, name.review) == ("to_check", None)


def test_the_free_float_follows_its_company_when_a_person_resolves_it(store, extracted):
    store.record_name_review(
        "maroc telecom",
        name_review(NameVerdict.same_as, party_id=issuer_id(store)),
        aggregates_of("maroc telecom"),
    )
    facts, _ = store.facts(ISIN)
    free_float = next(f for f in facts if f.values["percent"] == "45")
    assert free_float.parties[0].resolved.kind == PartyKind.free_float


def test_same_as_an_unknown_party_is_refused(store, extracted):
    with pytest.raises(LookupError):
        store.record_name_review(
            "societe alpha", name_review(NameVerdict.same_as, party_id="nobody"), []
        )


def test_a_re_extract_supersedes_facts_never_aliases_and_keeps_a_kept_value(store, extracted):
    link_issuer(store, extracted)
    facts, _ = store.facts()
    alpha = next(f for f in facts if f.values["percent"] == "53")
    store.record_review(
        [alpha.id],
        ReviewDraft(
            verdict=Verdict.accepted,
            reviewer="Z. Bajjou",
            reviewed_at=datetime(2026, 11, 12, 10, tzinfo=UTC),
        ),
    )
    extract_facts(store, extracted, minute=50)
    facts, _ = store.facts()
    assert len(facts) == 3
    again = next(f for f in facts if f.values["percent"] == "53")
    assert again.id != alpha.id
    assert again.review.verdict == Verdict.accepted
    # The issuer's name stays linked: Aliases belong to the name, not to a Run.
    assert again.parties[1].resolved.isin == ISIN
    assert store.fact(alpha.id).id == alpha.id


def test_every_organisation_has_an_id(store, document, driver):
    driver.execute_query("CREATE (:Organisation {isin: 'MA0000077777', name: 'Old'})")
    store.ensure_schema()
    records, _, _ = driver.execute_query(
        "MATCH (o:Organisation) WHERE o.id IS NULL RETURN count(o) AS missing"
    )
    assert records[0]["missing"] == 0


def test_a_decision_supersedes_the_link_it_replaces_which_is_kept(store, extracted, driver):
    link_issuer(store, extracted)
    store.record_name_review(
        "maroc telecom",
        name_review(NameVerdict.new, name="Maroc Telecom Bis", kind=PartyKind.company),
        aggregates_of("maroc telecom"),
    )
    records, _, _ = driver.execute_query(
        """
        MATCH (a:Alias)-[link:ALIAS_OF]->(o)
        WHERE a.key IN ['maroc telecom', 'free_float:maroc telecom']
        RETURN a.key AS key, o.name AS name, coalesce(link.superseded, false) AS superseded
        ORDER BY key, superseded
        """
    )
    assert [tuple(r.values()) for r in records] == [
        ("free_float:maroc telecom", "Free float", False),
        ("free_float:maroc telecom", "Free float", True),
        ("maroc telecom", "Maroc Telecom Bis", False),
        ("maroc telecom", "Maroc Telecom", True),
    ]
