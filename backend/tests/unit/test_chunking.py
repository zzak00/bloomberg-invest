"""The chunker's boundary rules (#19 R2): tables whole, paragraphs whole, long sections split,
no heading lost."""

from bloomberg_invest.domain.chunking import Block, SectionRef, chunk


def words(text: str) -> int:
    return len(text.split())


def heading(title: str, page: int = 1) -> Block:
    return Block(kind="heading", text=title, page=page)


def para(text: str, page: int = 1, numbered: bool = False) -> Block:
    return Block(kind="text", text=text, page=page, numbered=numbered)


def table(header: str, rows: list[str], page: int = 1, columns: int = 3) -> Block:
    return Block(kind="table", text="", page=page, header=header, rows=tuple(rows), columns=columns)


SECTIONS = [
    SectionRef(id="s1", title="1. RÉSULTATS", page=1),
    SectionRef(id="s2", title="NOTE 2. DIVIDENDES", page=2),
]


def test_a_section_s_paragraphs_form_one_chunk_and_a_table_its_own():
    blocks = [
        heading("1. RÉSULTATS"),
        para("Le chiffre d'affaires est stable."),
        table("| a | b | c |", ["| 1 | 2 | 3 |"]),
        para("Le résultat progresse."),
        heading("NOTE 2. DIVIDENDES", page=2),
        para("Le dividende proposé est de 5 dirhams.", page=2),
    ]
    chunks = chunk(blocks, SECTIONS, cap=100, count=words)

    assert [(c.kind, c.section_id) for c in chunks] == [
        ("text", "s1"),
        ("table", "s1"),
        ("text", "s2"),
    ]
    assert [p.text for p in chunks[0].paragraphs] == [
        "1. RÉSULTATS",
        "Le chiffre d'affaires est stable.",
        "Le résultat progresse.",
    ]
    assert [c.index for c in chunks] == [0, 1, 2]


def test_a_table_is_one_chunk_however_long():
    rows = [f"| {i} | x | y |" for i in range(500)]
    chunks = chunk([heading("1. RÉSULTATS"), table("| a | b | c |", rows)], SECTIONS, 50, words)

    [only] = chunks
    assert only.kind == "table"
    assert only.text.splitlines()[:2] == ["1. RÉSULTATS", ""]
    assert only.text.splitlines()[4:] == rows
    assert only.token_count > 50


def test_a_table_continued_on_the_next_page_is_joined_into_one_chunk():
    blocks = [
        heading("1. RÉSULTATS"),
        table("| a | b | c |", ["| 1 | 2 | 3 |"], page=1),
        table("| a | b | c |", ["| 4 | 5 | 6 |"], page=2),
    ]
    [only] = chunk(blocks, SECTIONS, cap=100, count=words)

    assert only.text.splitlines() == [
        "1. RÉSULTATS",
        "",
        "| a | b | c |",
        "| --- | --- | --- |",
        "| 1 | 2 | 3 |",
        "| 4 | 5 | 6 |",
    ]
    assert only.pages == (1, 2)


def test_tables_with_other_columns_or_on_the_same_page_stay_apart():
    blocks = [
        heading("1. RÉSULTATS"),
        table("| a | b | c |", ["| 1 | 2 | 3 |"], page=1),
        table("| a | b |", ["| 4 | 5 |"], page=2, columns=2),
        table("| c | d |", ["| 6 | 7 |"], page=2, columns=2),
    ]
    assert len(chunk(blocks, SECTIONS, cap=100, count=words)) == 3


def test_a_long_section_splits_at_its_numbered_points_first():
    blocks = [
        heading("1. RÉSULTATS"),
        para("intro " * 10),
        para("1) premier point " + "mot " * 20, numbered=True),
        para("suite du premier point " + "mot " * 5),
        para("2) second point " + "mot " * 20, numbered=True),
    ]
    chunks = chunk(blocks, SECTIONS, cap=50, count=words)

    assert [[p.text.split()[0] for p in c.paragraphs] for c in chunks] == [
        ["1.", "intro", "1)", "suite"],
        ["2)"],
    ]


def test_otherwise_a_long_section_splits_evenly_between_paragraphs():
    blocks = [heading("1. RÉSULTATS")] + [para(f"p{i} " + "mot " * 9) for i in range(6)]
    chunks = chunk(blocks, SECTIONS, cap=40, count=words)

    assert [len(c.paragraphs) for c in chunks] == [4, 3]
    assert all(c.token_count <= 40 for c in chunks)


def test_a_paragraph_is_never_split_even_over_the_cap():
    blocks = [heading("1. RÉSULTATS"), para("court"), para("long " * 80), para("court")]
    chunks = chunk(blocks, SECTIONS, cap=50, count=words)

    assert [len(p.text.split()) for c in chunks for p in c.paragraphs] == [2, 1, 80, 1]
    assert any(c.token_count > 50 and len(c.paragraphs) == 1 for c in chunks)


def test_a_repeated_heading_keeps_its_section_and_text_before_any_heading_joins_the_first():
    blocks = [
        para("Rapport financier annuel"),
        heading("1. RÉSULTATS"),
        para("Avant le saut de page."),
        heading("1. RÉSULTATS", page=2),
        para("Après le saut de page.", page=2),
    ]
    [only] = chunk(blocks, SECTIONS, cap=100, count=words)

    assert only.section_id == "s1"
    assert [p.text for p in only.paragraphs] == [
        "Rapport financier annuel",
        "1. RÉSULTATS",
        "Avant le saut de page.",
        "Après le saut de page.",
    ], "the repeated title is dropped"


def test_a_chunk_refers_to_the_notes_it_cites_but_not_its_own():
    blocks = [
        heading("1. RÉSULTATS"),
        para("Voir note 2 et cf. Note 2 ; la note 9 n'existe pas."),
        heading("NOTE 2. DIVIDENDES", page=2),
        para("Comme indiqué en note 2.", page=2),
    ]
    first, second = chunk(blocks, SECTIONS, cap=100, count=words)

    assert first.refers_to == ("s2",)
    assert second.refers_to == ()


def test_an_even_split_leaves_no_small_leftover():
    # Token counts of the fixture's "2. VUE D'ENSEMBLE" paragraphs: 610 in all, cap 200.
    sizes = [67, 60, 46, 43, 46, 43, 67, 60, 46, 43, 46, 43]
    blocks = [heading("1. RÉSULTATS")] + [para(" ".join(["mot"] * n)) for n in sizes]
    chunks = chunk(blocks, SECTIONS, cap=200, count=words)

    assert len(chunks) == 4
    assert all(130 <= c.token_count <= 200 for c in chunks), [c.token_count for c in chunks]


def test_a_sentence_taken_for_a_heading_stays_in_its_chunk():
    # Docling read the first line of a paragraph as a section header (golden p. 10).
    sections = [*SECTIONS[:1], SectionRef(id="s3", title="Le résultat net atteint 6 969", page=1)]
    blocks = [
        heading("1. RÉSULTATS"),
        para("Le chiffre d'affaires est stable."),
        heading("Le résultat net atteint 6 969"),
        para("millions de dirhams."),
    ]
    _, second = chunk(blocks, sections, cap=100, count=words)

    assert second.section_id == "s3"
    assert second.text == "Le résultat net atteint 6 969\n\nmillions de dirhams."


def test_a_heading_with_no_content_of_its_own_joins_the_next_chunk():
    sections = [*SECTIONS, SectionRef(id="s21", title="2.1 Distribution", page=2)]
    blocks = [
        heading("NOTE 2. DIVIDENDES", page=2),
        heading("2.1 Distribution", page=2),
        table("| a | b | c |", ["| 1 | 2 | 3 |"], page=2),
        heading("Sous-titre", page=2),
    ]
    first, last = chunk(blocks, sections, cap=100, count=words)

    assert (first.kind, first.section_id) == ("table", "s21")
    assert first.text.startswith("NOTE 2. DIVIDENDES\n\n2.1 Distribution\n\n| a | b | c |")
    assert first.refers_to == (), "a heading is not a citation"
    assert (last.kind, last.text) == ("text", "Sous-titre")
