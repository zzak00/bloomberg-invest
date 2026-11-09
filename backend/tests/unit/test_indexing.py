"""What search indexes for a Chunk: a header with where it sits, then its blocks, a table one
line per row."""

from bloomberg_invest.domain.chunking import Block, ChunkDraft
from bloomberg_invest.domain.indexing import index_text

PATH = ("NOTE 30. OPÉRATIONS AVEC LES PARTIES LIÉES", "30.4. Autres parties liées")


def draft(*blocks: Block, path: tuple[str, ...] = PATH, pages=(66,)) -> ChunkDraft:
    return ChunkDraft(
        index=0,
        kind="table" if blocks[-1].kind == "table" else "text",
        section_id="s",
        paragraphs=blocks,
        text="",
        token_count=0,
        pages=pages,
        refers_to=(),
        path=path,
    )


def test_the_header_gives_the_section_path_and_page_then_the_blocks_follow():
    chunk = draft(
        Block(kind="heading", text="30.4. Autres parties liées", page=66),
        Block(kind="text", text="Maroc Telecom a réalisé en 2025 des transactions.", page=66),
        Block(kind="text", text="Néant.", page=66),
    )

    assert index_text(chunk) == (
        "NOTE 30. OPÉRATIONS AVEC LES PARTIES LIÉES > 30.4. Autres parties liées · p. 66\n"
        "30.4. Autres parties liées\n\n"
        "Maroc Telecom a réalisé en 2025 des transactions.\n\n"
        "Néant."
    )


def test_a_chunk_over_several_pages_gives_their_range():
    chunk = draft(Block(kind="text", text="Suite.", page=66, last_page=67), pages=(66, 67))

    assert index_text(chunk).splitlines()[0].endswith("· pp. 66-67")


def test_a_chunk_before_any_section_has_only_its_page():
    chunk = draft(Block(kind="text", text="SOMMAIRE", page=2), path=(), pages=(2,))

    assert index_text(chunk) == "p. 2\nSOMMAIRE"


def test_a_table_reads_one_line_per_row_with_each_value_after_its_column():
    chunk = draft(
        Block(kind="heading", text="Exercice 2025", page=67),
        Block(
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
        ),
        pages=(67,),
    )

    assert index_text(chunk).splitlines() == [
        f"{' > '.join(PATH)} · p. 67",
        "Exercice 2025",
        "",
        "(En millions de MAD)",
        "Chiffre d'affaires: Etisalat 275 · EDCH 12",
        "Achats: EDCH 5",
    ]


def test_a_row_without_a_label_keeps_its_values_and_a_column_without_a_name_its_value():
    chunk = draft(
        Block(
            kind="table",
            text="",
            page=40,
            header="| Société | | % d'intérêt |",
            rows=("| | SA | 80% |", "| Avenue Annakhil Hay Riad Rabat-Maroc | | |"),
            columns=3,
        ),
        path=(),
        pages=(40,),
    )

    assert index_text(chunk).splitlines() == [
        "p. 40",
        "Société",
        "SA · % d'intérêt 80%",
        "Avenue Annakhil Hay Riad Rabat-Maroc",
    ]
