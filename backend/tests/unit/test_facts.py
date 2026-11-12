"""Facts stated in words (#24): a page's answer turned into checked drafts, the key a dossier row
groups them by, when two agree, and which value a row shows (#19 R6, R7, R8)."""

from datetime import UTC, date, datetime

from bloomberg_invest.domain.extraction import (
    CellPassage,
    SourceCell,
    SourceParagraph,
    SpanPassage,
    page_sources,
)
from bloomberg_invest.domain.facts import (
    SPECS,
    FactKind,
    FactRejection,
    Stated,
    agree,
    drafts,
    instructions,
    page_prompt,
    pages_with_text,
    row_key,
    schema,
    section_path,
    shown,
    values_of,
)
from bloomberg_invest.domain.names import PartyKind, alias_key, name_key

OWNERS = SourceParagraph(
    27,
    "Au 31 décembre 2025, le capital est réparti comme suit : - Société Alpha : 53% ; "
    "- Royaume du Maroc : 22% ; - Autres : 25%.",
    ((27, 50.0, 300.0, 540.0, 330.0),),
)
DIVIDEND = SourceParagraph(
    10,
    "Au titre de l'exercice 2025, le Conseil propose la distribution d’un dividende de 4,00 "
    "dirhams par action, représentant "
    "un montant global de 3,5 milliards de dirhams.",
    ((10, 50.0, 300.0, 540.0, 330.0),),
)


def cell(row: int, col: int, text: str) -> SourceCell:
    return SourceCell(f"cell-{row}-{col}", 2, 40, row, col, 1, text, (0, 0, 1, 1))


SCOPE_TABLE = [
    cell(0, 0, "Société"),
    cell(0, 1, "% d'intérêt"),
    cell(0, 2, "% de contrôle"),
    cell(0, 3, "Méthode 31-déc.-25"),
    cell(1, 0, "Beta Mobile SA"),
    cell(1, 1, "80%"),
    cell(1, 2, "80%"),
    cell(1, 3, "IG"),
]


def party(written: str, name: str | None = None, kind: str = "company") -> dict:
    return {"written": written, "name": name or written, "kind": kind}


def holding(holder: dict, percent: str | None, quote: str, source_id: str = "p27.0") -> dict:
    return {
        "holder": holder,
        "held": party("Groupe Gamma", "Gamma Telecom"),
        "percent": percent,
        "shares": None,
        "rights": "capital",
        "as_of": "2025-12-31",
        "source_id": source_id,
        "quote": quote,
    }


def answer(**lists) -> dict:
    return {kind.value: lists.get(kind.value, []) for kind in FactKind}


def page27():
    return page_sources(27, [OWNERS], [])


def test_a_holding_quoted_from_its_paragraph_is_a_fact_naming_both_parties():
    [fact] = drafts(
        answer(shareholding=[holding(party("Société Alpha"), "53", "Société Alpha : 53%")]),
        page27(),
    )
    assert fact.rejected is None
    assert fact.kind == FactKind.shareholding
    assert fact.passage == SpanPassage(27, "Société Alpha : 53%", OWNERS.text, OWNERS.boxes)
    assert [(n.role, n.name, n.key) for n in fact.names] == [
        ("holder", "Société Alpha", "societe alpha"),
        ("held", "Gamma Telecom", "gamma telecom"),
    ]
    assert fact.values["percent"] == "53"


def test_a_quote_that_is_not_in_the_paragraph_is_rejected():
    [fact] = drafts(
        answer(shareholding=[holding(party("Société Alpha"), "53", "Société Alpha détient 53%")]),
        page27(),
    )
    assert fact.rejected == FactRejection.quote_not_in_source


def test_a_number_the_quote_does_not_state_is_rejected():
    """A misread 55 % on a correct quote never becomes a Fact (D2)."""
    [fact] = drafts(
        answer(shareholding=[holding(party("Société Alpha"), "55", "Société Alpha : 53%")]),
        page27(),
    )
    assert fact.rejected == FactRejection.number_not_in_quote


def test_a_holding_with_no_percentage_or_share_count_states_nothing():
    [fact] = drafts(
        answer(shareholding=[holding(party("Société Alpha"), None, "Société Alpha")]), page27()
    )
    assert fact.rejected == FactRejection.no_value


def test_an_unknown_source_id_is_rejected():
    [fact] = drafts(
        answer(shareholding=[holding(party("Société Alpha"), "53", "53%", "p27.9")]), page27()
    )
    assert (fact.rejected, fact.passage) == (FactRejection.unknown_source, None)


def test_quotes_forgive_accents_apostrophes_and_spacing():
    item = {
        "company": party("Gamma"),
        "measure": "per_share",
        "amount": "4,00",
        "unit": "MAD",
        "status": "proposed",
        "fiscal_year": 2025,
        "source_id": "p10.0",
        "quote": "distribution d'un  dividende de 4,00 dirhams",
    }
    [fact] = drafts(answer(dividend=[item]), page_sources(10, [DIVIDEND], []))
    assert fact.rejected is None
    assert (fact.amount_value, fact.scale, fact.currency) == ("4", 1, "MAD")
    assert fact.period == (date(2025, 1, 1), date(2025, 12, 31))


def test_a_total_dividend_is_kept_in_its_base_unit():
    item = {
        "company": party("Gamma"),
        "measure": "total",
        "amount": "3,5",
        "unit": "MAD billions",
        "status": "proposed",
        "fiscal_year": 2025,
        "source_id": "p10.0",
        "quote": "un montant global de 3,5 milliards de dirhams",
    }
    [fact] = drafts(answer(dividend=[item]), page_sources(10, [DIVIDEND], []))
    assert (fact.amount_value, fact.scale) == ("3500000000", 1_000_000_000)


def test_a_fact_read_from_a_table_cell_states_its_row():
    """A consolidation row's percentages sit in two cells; the fact cites one and states the
    row."""
    item = {
        "parent": party("Gamma Telecom"),
        "subsidiary": party("Beta Mobile SA", "Beta Mobile"),
        "interest": "80",
        "control": "80",
        "method": "full",
        "as_of": "2025-12-31",
        "source_id": "t40.0.r1.c1",
        "quote": "Beta Mobile SA 80% 80% IG",
    }
    [fact] = drafts(answer(consolidation=[item]), page_sources(40, [], SCOPE_TABLE))
    assert fact.rejected is None
    assert fact.passage == CellPassage("cell-1-1")


def test_an_unreadable_date_is_rejected():
    item = holding(party("Société Alpha"), "53", "Société Alpha : 53%") | {"as_of": "fin 2025"}
    [fact] = drafts(answer(shareholding=[item]), page27())
    assert fact.rejected == FactRejection.unreadable_date


def test_free_float_is_keyed_by_the_company_whose_holders_it_stands_for():
    [fact] = drafts(
        answer(
            shareholding=[
                holding(party("Autres", "Free float", "free_float"), "25", "Autres : 25%")
            ]
        ),
        page27(),
    )
    assert fact.names[0].key == "free_float:gamma telecom"


def test_names_match_whatever_their_case_accents_and_legal_form():
    assert name_key("Maroc Télécom SA") == name_key("MAROC TELECOM") == "maroc telecom"
    assert name_key("Itissalat Al-Maghrib (IAM) S.A") == "itissalat al maghrib"
    assert name_key("Groupe Gamma") == "gamma"
    assert name_key("S.A.") == ""
    assert alias_key("actions propres", PartyKind.treasury_shares, "gamma") == (
        "treasury_shares:gamma"
    )


def test_every_page_with_a_paragraph_or_a_table_is_read():
    assert pages_with_text([OWNERS, DIVIDEND], SCOPE_TABLE) == [10, 27, 40]


def test_the_schema_asks_every_kind_with_every_field():
    answer_schema = schema()
    assert answer_schema["required"] == [k.value for k in FactKind]
    shareholding = answer_schema["properties"]["shareholding"]["items"]
    assert shareholding["required"] == [
        "holder",
        "held",
        "percent",
        "shares",
        "rights",
        "as_of",
        "source_id",
        "quote",
    ]
    assert shareholding["properties"]["percent"]["type"] == ["string", "null"]
    assert "- consolidation:" in instructions("Prompt.\n")


# Agreement, Conflict and the value shown (#19 R8).


def stated(
    percent: str | None,
    when: date = date(2025, 12, 31),
    *,
    id: str = "f1",
    holder: str = "alpha",
    annual: bool = True,
    day: int = 1,
    kept: bool = False,
    kind: FactKind = FactKind.shareholding,
    **values,
) -> Stated:
    base = {"percent": percent, "shares": None, "rights": "capital", "as_of": when.isoformat()}
    return Stated(
        id=id,
        kind=kind,
        parties=(("holder", holder), ("held", "org-gamma")),
        values=base | values,
        scale=None,
        when=when,
        annual=annual,
        recorded_at=datetime(2026, 11, day, tzinfo=UTC),
        kept=kept,
    )


def test_a_row_is_a_holding_of_one_holder_in_one_company_whatever_its_date():
    assert row_key(stated("53")) == row_key(stated("50", date(2024, 12, 31)))
    assert row_key(stated("53")) != row_key(stated("53", holder="beta"))
    assert row_key(stated("53")) != row_key(stated("53", rights="voting"))


def test_fiscal_year_kinds_have_a_row_per_year():
    opinion = {"basis_scope": "consolidated", "opinion": "unqualified", "emphasis": False}
    a = stated(None, kind=FactKind.auditor_opinion, fiscal_year=2025, **opinion)
    b = stated(None, kind=FactKind.auditor_opinion, fiscal_year=2024, **opinion)
    assert row_key(a) != row_key(b)


def test_numbers_agree_within_the_precision_they_are_written_to():
    assert agree(stated("53"), stated("53,0"))
    assert agree(stated("41,2"), stated("41"))
    assert not agree(stated("53"), stated("55"))
    # A value one leaves unstated agrees with any.
    assert agree(stated("53"), stated("53", shares="466 000 000"))


def test_texts_agree_whatever_their_case_and_accents():
    a = stated(None, kind=FactKind.consolidation, method="full", interest="80", control="80")
    b = stated(None, kind=FactKind.consolidation, method="full", interest="80,0", control="80")
    c = stated(None, kind=FactKind.consolidation, method="equity", interest="80", control="80")
    assert agree(a, b) and not agree(a, c)
    assert len(values_of([a, b, c])) == 2


def test_a_row_shows_the_latest_date():
    row = shown([stated("50", date(2024, 12, 31), id="old"), stated("53", id="new")])
    assert (row.fact.id, row.why, row.conflict) == ("new", "latest", False)


def test_two_values_at_the_latest_date_are_a_conflict_the_annual_report_wins():
    issuer_page = stated("54", id="issuer", annual=False, day=1)
    annual = stated("53", id="annual", day=2)
    row = shown([issuer_page, annual])
    assert (row.fact.id, row.why, row.conflict) == ("annual", "annual_report", True)
    assert [[f.id for f in g] for g in row.others] == [["issuer"]]


def test_two_annual_reports_disagreeing_show_the_first_recorded():
    row = shown([stated("53", id="later", day=5), stated("54", id="first", day=2)])
    assert (row.fact.id, row.why) == ("first", "earliest")


def test_a_kept_value_is_shown_whatever_its_source_and_stays_a_conflict():
    row = shown([stated("53", id="annual"), stated("54", id="issuer", annual=False, kept=True)])
    assert (row.fact.id, row.why, row.conflict) == ("issuer", "kept", True)


def test_a_value_kept_at_an_earlier_date_gives_way_to_a_later_one():
    row = shown([stated("50", date(2024, 12, 31), id="old", kept=True), stated("53", id="new")])
    assert (row.fact.id, row.kept_earlier) == ("new", True)


def test_a_proposed_and_a_paid_dividend_of_one_year_are_one_row_compared_by_amount():
    def dividend(amount: str, status: str, id: str) -> Stated:
        return stated(
            None,
            id=id,
            kind=FactKind.dividend,
            measure="per_share",
            amount=amount,
            unit="MAD",
            status=status,
            fiscal_year=2025,
        )

    proposed, paid = dividend("4,00", "proposed", "p"), dividend("4", "paid", "q")
    assert row_key(proposed) == row_key(paid)
    assert shown([proposed, paid]).conflict is False
    # The meeting changed it: that is a Conflict to see, not two dividends.
    assert shown([proposed, dividend("3,50", "paid", "r")]).conflict is True


def test_agreeing_facts_of_two_filings_are_one_value_shown_once():
    row = shown([stated("53", id="a", day=1), stated("53,0", id="b", day=3)])
    assert row.conflict is False
    assert [f.id for f in row.agreeing] == ["a", "b"]


def test_every_kind_has_roles_and_a_time():
    for spec in SPECS.values():
        assert spec.roles and spec.time in ("as_of", "fiscal_year")


RELATED = [
    cell(2, 0, "Exercice 2025"),
    cell(3, 0, "Créances"),
    cell(3, 1, "46"),
    cell(3, 2, "111"),
    cell(3, 3, "17"),
]


def test_numbers_of_a_table_row_are_read_cell_by_cell():
    """`46` and `111` in two cells are never the one number `46 111`."""
    item = {
        "company": party("Gamma"),
        "counterparty": party("Alpha"),
        "nature": "receivables",
        "amount": "46",
        "unit": "MAD millions",
        "fiscal_year": 2025,
        "source_id": "t40.0.r3.c1",
        "quote": "Créances | 46 | 111 | 17",
    }
    [fact] = drafts(answer(related_party_agreement=[item]), page_sources(40, [], RELATED))
    assert fact.rejected is None


def test_a_quote_may_run_on_into_the_paragraphs_after_the_one_cited():
    """A signature block: the firm, its partner and the title, each its own paragraph."""
    block = [
        SourceParagraph(89, "Deloitte Alpha", ()),
        SourceParagraph(89, "Jean ALPHA", ()),
        SourceParagraph(89, "Associé", ()),
        SourceParagraph(89, "Rapport sur l'exercice clos le 31 décembre 2025", ()),
    ]
    item = {
        "auditor": party("Deloitte Alpha", kind="audit_firm"),
        "company": party("Gamma"),
        "basis_scope": "company-only",
        "partner": "Jean Alpha",
        "fiscal_year": 2025,
        "source_id": "p89.0",
        "quote": "Deloitte Alpha\nJean ALPHA\nAssocié",
    }
    [fact] = drafts(answer(audit_mandate=[item]), page_sources(89, block, []))
    assert fact.rejected is None
    item = item | {"source_id": "p89.2"}
    [fact] = drafts(answer(audit_mandate=[item]), page_sources(89, block, []))
    assert fact.rejected == FactRejection.quote_not_in_source


def test_a_dividend_in_dirham_singular_has_its_currency():
    item = {
        "company": party("Gamma"),
        "measure": "per_share",
        "amount": "4,00",
        "unit": "dirham",
        "status": "proposed",
        "fiscal_year": 2025,
        "source_id": "p10.0",
        "quote": "un dividende de 4,00 dirhams",
    }
    [fact] = drafts(answer(dividend=[item]), page_sources(10, [DIVIDEND], []))
    assert (fact.rejected, fact.currency) == (None, "MAD")


SIGNATURES = [
    cell(3, 0, "Exercice 2025"),
    cell(0, 0, "Deloitte Alpha"),
    cell(0, 1, "Beta Audit SA"),
    cell(1, 0, "Jean ALPHA"),
    cell(1, 1, "Marie BETA"),
    cell(2, 0, "Associé"),
    cell(2, 1, "Associé"),
]


def test_a_table_states_a_fact_down_a_column_too():
    item = {
        "auditor": party("Beta Audit SA", kind="audit_firm"),
        "company": party("Gamma"),
        "basis_scope": "company-only",
        "partner": "Marie Beta",
        "fiscal_year": 2025,
        "source_id": "t40.0.r0.c1",
        "quote": "Beta Audit SA\nMarie BETA\nAssocié",
    }
    [fact] = drafts(answer(audit_mandate=[item]), page_sources(40, [], SIGNATURES))
    assert fact.rejected is None


def test_a_stake_the_table_calls_not_significant_is_a_fact():
    stakes = [cell(0, 1, "31/12/2025"), cell(4, 0, "Delta Sat"), cell(4, 1, "NS")]
    item = holding(party("Gamma"), "NS", "Delta Sat | NS", "t40.0.r4.c1") | {
        "held": party("Delta Sat")
    }
    [fact] = drafts(answer(shareholding=[item]), page_sources(40, [], stakes))
    assert fact.rejected is None
    # Not where the row writes a number.
    item = item | {"quote": "Delta Sat"}
    stakes = [cell(0, 1, "31/12/2025"), cell(4, 0, "Delta Sat"), cell(4, 1, "5%")]
    [fact] = drafts(answer(shareholding=[item]), page_sources(40, [], stakes))
    assert fact.rejected == FactRejection.unreadable_number


def test_facts_one_run_recorded_at_once_are_ordered_as_the_filing_reads():
    from dataclasses import replace

    second = replace(stated("54", id="a"), place=(27, 300.0, 50.0, 80.0))
    first = replace(stated("53", id="b"), place=(27, 300.0, 50.0, 20.0))
    assert shown([second, first]).fact.id == "b"


def test_a_year_the_page_never_writes_is_rejected():
    """A made-up date never decides which value the dossier shows (#19 R8)."""
    item = holding(party("Société Alpha"), "53", "Société Alpha : 53%") | {"as_of": "2019-12-31"}
    [fact] = drafts(answer(shareholding=[item]), page27())
    assert fact.rejected == FactRejection.year_not_on_page


def test_a_year_ending_a_table_date_is_on_the_page():
    """`31-déc.-25` heads the column: the scope table's facts hold on 2025-12-31."""
    item = {
        "parent": party("Gamma Telecom"),
        "subsidiary": party("Beta Mobile"),
        "interest": "80",
        "control": "80",
        "method": "full",
        "as_of": "2024-12-31",
        "source_id": "t40.0.r1.c1",
        "quote": "Beta Mobile SA 80% 80% IG",
    }
    [fact] = drafts(answer(consolidation=[item]), page_sources(40, [], SCOPE_TABLE))
    assert fact.rejected == FactRejection.year_not_on_page


def test_a_table_fact_s_first_number_is_in_the_cell_it_cites():
    """Voting rights read from the interest column are refused, though the row holds both."""
    table = [
        cell(0, 1, "% intérêt 31-déc.-25"),
        cell(1, 0, "Beta Mobile"),
        cell(1, 1, "41,2%"),
        cell(1, 2, "51,5%"),
    ]
    item = holding(party("Gamma"), "51,5", "Beta Mobile 41,2% 51,5%", "t40.0.r1.c1") | {
        "held": party("Beta Mobile"),
        "rights": "voting",
    }
    [fact] = drafts(answer(shareholding=[item]), page_sources(40, [], table))
    assert fact.rejected == FactRejection.not_in_cited_cell


def test_a_page_is_shown_with_the_sections_it_is_in():
    headings = [
        ("3. COMPTES CONSOLIDES", 1, 20),
        ("NOTE 2. PERIMETRE", 2, 40),
        ("RAPPORT DES COMMISSAIRES AUX COMPTES", 2, 73),
        ("4. COMPTES SOCIAUX", 1, 78),
    ]
    assert section_path(headings, 77) == [
        "3. COMPTES CONSOLIDES",
        "RAPPORT DES COMMISSAIRES AUX COMPTES",
    ]
    assert section_path(headings, 80) == ["4. COMPTES SOCIAUX"]
    assert section_path(headings, 5) == []
    assert page_prompt(page27(), ["4. COMPTES SOCIAUX"]).startswith(
        "Section: 4. COMPTES SOCIAUX\nPage 27"
    )


def test_a_listing_naming_only_its_company_and_exchange_is_a_fact():
    paragraph = SourceParagraph(
        52, "En 2025, un contrat de liquidité a été conclu à la bourse de Paris.", ()
    )
    item = {
        "company": party("Gamma"),
        "exchange": party("bourse de Paris", "Bourse de Paris"),
        "ticker": None,
        "isin": None,
        "compartment": None,
        "sector": None,
        "as_of": "2025-12-31",
        "source_id": "p52.0",
        "quote": "un contrat de liquidité a été conclu à la bourse de Paris",
    }
    [fact] = drafts(answer(listing=[item]), page_sources(52, [paragraph], []))
    assert fact.rejected is None


def test_a_year_in_the_page_s_sections_is_on_the_page():
    """A signature page never writes its year; the report's heading does."""
    item = {
        "auditor": party("Beta Audit SA", kind="audit_firm"),
        "company": party("Gamma"),
        "basis_scope": "consolidated",
        "partner": "Marie Beta",
        "fiscal_year": 2025,
        "source_id": "t40.0.r0.c1",
        "quote": "Beta Audit SA\nMarie BETA\nAssocié",
    }
    signatures = [c for c in SIGNATURES if c.text != "Exercice 2025"]
    sources = page_sources(40, [], signatures)
    [fact] = drafts(answer(audit_mandate=[item]), sources)
    assert fact.rejected == FactRejection.year_not_on_page
    [fact] = drafts(answer(audit_mandate=[item]), sources, ["COMPTES AU 31 DECEMBRE 2025"])
    assert fact.rejected is None


def test_a_quote_may_be_a_row_s_label_then_the_cited_cell():
    table = [
        cell(0, 1, "31-déc.-25"),
        cell(5, 0, "Total (b)"),
        cell(5, 1, "1 924"),
        cell(5, 2, "3 691"),
    ]
    item = {
        "company": party("Gamma"),
        "measure": "total",
        "amount": "3 691",
        "unit": "MAD millions",
        "status": "paid",
        "fiscal_year": 2025,
        "source_id": "t40.0.r5.c2",
        "quote": "Total (b) 3 691",
    }
    [fact] = drafts(answer(dividend=[item]), page_sources(40, [], table))
    assert fact.rejected is None
    # Not a label the row does not write.
    item = item | {"quote": "Total (a) 3 691"}
    [fact] = drafts(answer(dividend=[item]), page_sources(40, [], table))
    assert fact.rejected == FactRejection.quote_not_in_source
