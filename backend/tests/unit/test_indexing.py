"""What search indexes for a Paragraph: where it sits, then its text, a table one line per row."""

from bloomberg_invest.domain.chunking import Block
from bloomberg_invest.domain.indexing import index_text, is_search_unit

PATH = ["NOTE 30. OPÉRATIONS AVEC LES PARTIES LIÉES", "30.4. Autres parties liées"]


def test_a_heading_is_not_searched_on_its_own():
    assert not is_search_unit(Block(kind="heading", text="Exercice 2025", page=67))
    assert is_search_unit(Block(kind="text", text="Néant.", page=70))
    assert is_search_unit(Block(kind="table", text="", page=67, header="| a | b |"))


def test_text_follows_its_section_path_and_page():
    block = Block(kind="text", text="Maroc Telecom a réalisé en 2025 des transactions.", page=66)

    assert index_text(block, PATH) == (
        "NOTE 30. OPÉRATIONS AVEC LES PARTIES LIÉES > 30.4. Autres parties liées · p. 66\n"
        "Maroc Telecom a réalisé en 2025 des transactions."
    )


def test_text_before_any_section_has_only_its_page():
    assert index_text(Block(kind="text", text="SOMMAIRE", page=2), []) == "p. 2\nSOMMAIRE"


def test_a_table_reads_one_line_per_row_with_each_value_after_its_column():
    block = Block(
        kind="table",
        text="| (En millions de MAD) | Etisalat | EDCH |\n| --- | --- | --- |\n...",
        page=67,
        header="| (En millions de MAD)   |   Etisalat |   EDCH |",
        rows=(
            "| Chiffre d'affaires     |        275 |     12 |",
            "| Achats                 |            |      5 |",
            "|                        |            |        |",
        ),
        columns=3,
    )

    assert index_text(block, [*PATH, "Exercice 2025"]).splitlines() == [
        f"{' > '.join(PATH)} > Exercice 2025 · p. 67",
        "(En millions de MAD)",
        "Chiffre d'affaires: Etisalat 275 · EDCH 12",
        "Achats: EDCH 5",
    ]


def test_a_row_without_a_label_keeps_its_values_and_a_column_without_a_name_its_value():
    block = Block(
        kind="table",
        text="",
        page=40,
        header="| Société | | % d'intérêt |",
        rows=("| | SA | 80% |", "| Avenue Annakhil Hay Riad Rabat-Maroc | | |"),
        columns=3,
    )

    assert index_text(block, []).splitlines() == [
        "p. 40",
        "Société",
        "SA · % d'intérêt 80%",
        "Avenue Annakhil Hay Riad Rabat-Maroc",
    ]
