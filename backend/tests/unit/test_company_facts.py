"""Facts of the eight other kinds as the dossier and the inspector state them (#24 AC4): one
sentence each, its value marked, naming each party as resolved or as the extractor read it."""

from datetime import UTC, date, datetime

from builders import DOCUMENT

from bloomberg_invest.domain.facts import FactKind
from bloomberg_invest.service_layer.company_facts import sentence
from bloomberg_invest.views import EntityRef, Party, Passage, StatedFact


def party(role: str, name: str, entity: str | None = None) -> Party:
    return Party(
        role=role,
        written=name,
        name=name,
        alias=name.lower(),
        entity=EntityRef(id="e1", name=entity, kind="company") if entity else None,
    )


def fact(kind: FactKind, parties: list[Party], fiscal_year: int | None = None, **values):
    return StatedFact(
        id="f1",
        kind=kind,
        parties=parties,
        values=values,
        as_of=None if fiscal_year else date(2025, 12, 31),
        fiscal_year=fiscal_year,
        quote="…",
        recorded_at=datetime(2026, 11, 12, tzinfo=UTC),
        document=DOCUMENT,
        passage=Passage(kind="span", page=27, boxes=[], text="…", quote="…"),
        page=27,
        review=None,
    )


def text(f) -> tuple[str, str, str]:
    s = sentence(f)
    return (s.before, s.value, s.after)


def test_a_holding_names_its_parties_as_resolved_or_as_read():
    holding = fact(
        FactKind.shareholding,
        [party("holder", "IAM", entity="Maroc Telecom"), party("held", "Beta Mobile SA")],
        percent="80",
        shares=None,
        rights="capital",
    )
    assert text(holding) == ("Maroc Telecom holds ", "80 %", " of Beta Mobile SA")


def test_voting_rights_and_a_share_count_say_so():
    holding = fact(
        FactKind.shareholding,
        [party("holder", "Alpha"), party("held", "Gamma")],
        percent=None,
        shares="466 000 000",
        rights="voting",
    )
    assert text(holding) == ("Alpha holds ", "466 000 000 shares", " of Gamma (voting rights)")


def test_a_dividend_says_whether_it_is_proposed_per_share_and_for_which_year():
    dividend = fact(
        FactKind.dividend,
        [party("company", "Gamma")],
        fiscal_year=2025,
        measure="per_share",
        amount="4,00",
        unit="MAD",
        status="proposed",
    )
    assert text(dividend) == ("Gamma proposes a dividend of ", "4,00 MAD", " per share for FY2025")


def test_an_opinion_marks_the_opinion_and_its_emphasis_of_matter():
    opinion = fact(
        FactKind.auditor_opinion,
        [party("company", "Gamma")],
        fiscal_year=2025,
        basis_scope="consolidated",
        opinion="unqualified",
        emphasis=True,
    )
    assert text(opinion) == (
        "The auditors' opinion on Gamma's consolidated accounts for FY2025 is ",
        "unqualified",
        ", with an emphasis of matter",
    )


def test_a_consolidated_subsidiary_states_its_interest_and_method():
    consolidation = fact(
        FactKind.consolidation,
        [party("parent", "Gamma"), party("subsidiary", "Beta")],
        interest="51",
        control="51",
        method="full",
    )
    assert text(consolidation) == ("Gamma holds ", "51 %", " of Beta, fully consolidated")


def test_a_board_seat_names_the_body():
    seat = fact(
        FactKind.board_seat,
        [party("member", "Lamia Alpha"), party("company", "Gamma")],
        body="audit_committee",
        role="member",
        status="appointed",
    )
    assert text(seat) == ("Lamia Alpha was appointed ", "member", " of Gamma's audit committee")
