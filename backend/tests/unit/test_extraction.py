"""A page shown to the LLM, and its answer turned into checked figure drafts (#19 R5, R6)."""

from datetime import date

import pytest

from bloomberg_invest import config
from bloomberg_invest.domain.extraction import (
    CellPassage,
    Rejection,
    SourceCell,
    SourceParagraph,
    SpanPassage,
    drafts,
    instructions,
    page_sources,
    pages_to_extract,
    schema,
)


def cell(row: int, col: int, text: str, table: int = 3, page: int = 24) -> SourceCell:
    return SourceCell(f"cell-{table}-{row}-{col}", table, page, row, col, 1, text, (0, 0, 1, 1))


CELLS = [
    cell(0, 0, "(En millions MAD)"),
    cell(0, 1, "31-déc.-24"),
    cell(0, 2, "31-déc.-25"),
    cell(1, 0, "Chiffre d'affaires"),
    cell(1, 1, "36 699"),
    cell(1, 2, "36 681"),
    cell(2, 0, "Résultat net"),
    cell(2, 1, "(988)"),
    cell(2, 2, "n.s."),
    cell(0, 0, "Autre table", table=4, page=25),
]
DIVIDEND = SourceParagraph(
    10,
    "Le résultat progresse. Le Conseil propose un dividende de 4,01 dirhams par action.",
    ((10, 50.0, 300.0, 540.0, 330.0),),
)
PARAGRAPHS = [
    SourceParagraph(24, "ÉTAT DE RÉSULTAT GLOBAL", ((24, 50.0, 40.0, 300.0, 60.0),)),
    DIVIDEND,
    SourceParagraph(2, "Sommaire", ()),
]


@pytest.fixture(scope="module")
def label_map():
    return config.label_map()


def figure(source_id: str, value: str, **overrides) -> dict:
    return {
        "line_item": "revenue",
        "fiscal_year": 2025,
        "basis_scope": "consolidated",
        "breakdown": "",
        "source_id": source_id,
        "value_as_written": value,
        "unit_scale": "MAD millions",
    } | overrides


def test_only_pages_with_a_table_or_a_digit_are_sent():
    assert pages_to_extract(PARAGRAPHS, CELLS) == [10, 24, 25]


def test_a_page_shows_its_paragraphs_and_tables_with_ids():
    sources = page_sources(24, PARAGRAPHS, CELLS)
    assert sources.prompt.splitlines()[:5] == [
        "Page 24",
        "",
        "Paragraphs:",
        "[p24.0] ÉTAT DE RÉSULTAT GLOBAL",
        "",
    ]
    assert '<table id="t24.0">' in sources.prompt
    assert '<td id="t24.0.r1.c2">36 681</td>' in sources.prompt
    assert '<td id="t24.0.r1.c0">Chiffre d&#x27;affaires</td>' in sources.prompt
    assert "Autre table" not in sources.prompt, "another page's table"
    assert sources.cells["t24.0.r1.c2"].id == "cell-3-1-2"


def test_the_llm_reads_the_prompt_then_every_line_item(label_map):
    text = instructions(config.extract_prompt().text, label_map)
    assert "Line items:\n- revenue: Revenue (chiffre d'affaires)" in text
    assert schema(label_map)["properties"]["figures"]["items"]["properties"]["line_item"][
        "enum"
    ] == list(label_map.items)


def test_a_figure_matching_its_cell_is_parsed_with_its_row_label(label_map):
    sources = page_sources(24, PARAGRAPHS, CELLS)
    [draft] = drafts({"figures": [figure("t24.0.r1.c2", "36 681")]}, sources, label_map)
    assert draft.rejected is None
    assert draft.passage == CellPassage("cell-3-1-2")
    assert draft.label == "Chiffre d'affaires"
    assert (draft.value, draft.unit, draft.scale, draft.currency) == (
        "36681000000",
        "MAD",
        1_000_000,
        "MAD",
    )
    assert (draft.basis_scope, draft.basis_standard) == ("consolidated", "IFRS")
    assert (draft.period.start, draft.period.end) == (date(2025, 1, 1), date(2025, 12, 31))


def test_a_balance_holds_on_the_year_end_and_company_only_means_cgnc(label_map):
    sources = page_sources(24, PARAGRAPHS, CELLS)
    item = figure("t24.0.r2.c1", "-988", line_item="equity", basis_scope="company-only")
    [draft] = drafts({"figures": [item]}, sources, label_map)
    assert draft.rejected is None
    assert draft.period.as_of == date(2025, 12, 31)
    assert draft.basis_standard == "CGNC"
    assert draft.label == "Résultat net"


def test_a_paragraph_figure_cites_the_quoted_span(label_map):
    sources = page_sources(10, PARAGRAPHS, CELLS)
    item = figure("p10.0", "4,01", line_item="dividend_per_share", unit_scale="MAD per share")
    [draft] = drafts({"figures": [item]}, sources, label_map)
    assert draft.rejected is None
    assert draft.passage == SpanPassage(10, "4,01", DIVIDEND.text, DIVIDEND.boxes)
    assert draft.label == "Le Conseil propose un dividende de 4,01 dirhams par action."
    assert (draft.value, draft.unit) == ("4.01", "MAD/share")


@pytest.mark.parametrize(
    ("item", "reason"),
    [
        (figure("t24.0.r1.c2", "36 699"), Rejection.value_differs),
        (figure("t24.0.r9.c9", "36 681"), Rejection.unknown_source),
        (figure("p24.0", "36 681"), Rejection.not_in_paragraph),
        (figure("t24.0.r2.c2", "n.s."), Rejection.value_differs),
        (figure("t24.0.r1.c2", "36 681", unit_scale="units"), Rejection.unknown_unit),
        (figure("t24.0.r1.c2", "36 681", line_item="goodwill"), Rejection.unknown_line_item),
        (figure("t24.0.r1.c2", "36 681", basis_scope="group"), Rejection.unknown_scope),
    ],
)
def test_a_figure_that_fails_its_check_is_rejected_with_the_reason(item, reason, label_map):
    sources = page_sources(24, PARAGRAPHS, CELLS)
    [draft] = drafts({"figures": [item]}, sources, label_map)
    assert draft.rejected == reason
    assert draft.value is None
