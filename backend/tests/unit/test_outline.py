"""The section tree is inferred from heading numbering: Docling reports every heading at level 1."""

from bloomberg_invest.adapters.parsing.outline import Heading, build_outline


def h(title: str, page: int = 1) -> Heading:
    return Heading(title=title, page=page, bbox=None)


def tree(sections, depth=0) -> list[str]:
    lines = []
    for s in sections:
        lines.append("  " * depth + s.title)
        lines += tree(s.children, depth + 1)
    return lines


def test_headings_before_the_first_chapter_stay_at_the_top():
    out = build_outline([h("2025 Rapport financier annuel"), h("SOMMAIRE", 2)])
    assert tree(out) == ["2025 Rapport financier annuel", "SOMMAIRE"]


def test_numbering_gives_the_depth_and_unnumbered_headings_hang_under_the_last_numbered_one():
    out = build_outline(
        [
            h("1. RÉSULTATS CONSOLIDÉS DES TROIS DERNIERS EXERCICES", 4),
            h("1.1 Chiffres consolidés en dirham", 4),
            h("État de résultat global", 4),
            h("État de la situation financière", 4),
            h("2. VUE D'ENSEMBLE", 6),
            h("2.2. Résultats comparés par zone géographique", 9),
            h("2.2.1. Comparaison des données 2024 et 2025", 9),
            h("2.2.1.1. Résultats consolidés du Groupe", 9),
            h("Chiffre d'affaires", 9),
            h("2.2.1.2. Activités au Maroc", 11),
        ]
    )
    assert tree(out) == [
        "1. RÉSULTATS CONSOLIDÉS DES TROIS DERNIERS EXERCICES",
        "  1.1 Chiffres consolidés en dirham",
        "    État de résultat global",
        "    État de la situation financière",
        "2. VUE D'ENSEMBLE",
        "  2.2. Résultats comparés par zone géographique",
        "    2.2.1. Comparaison des données 2024 et 2025",
        "      2.2.1.1. Résultats consolidés du Groupe",
        "        Chiffre d'affaires",
        "      2.2.1.2. Activités au Maroc",
    ]


def test_a_chapter_heading_repeated_on_the_next_page_is_dropped():
    out = build_outline(
        [h("2. VUE D'ENSEMBLE", 6), h("2. VUE D'ENSEMBLE", 7), h("2.1. Périmètre", 7)]
    )
    assert tree(out) == ["2. VUE D'ENSEMBLE", "  2.1. Périmètre"]
    assert out[0].page == 6


def test_notes_sit_under_their_chapter_with_their_own_numbering():
    out = build_outline(
        [
            h("3. COMPTES CONSOLIDÉS DU GROUPE", 23),
            h("NOTE 1. PRINCIPES COMPTABLES", 28),
            h("1. CONTEXTE DE L'ÉLABORATION", 28),
            h("2. CONFORMITÉ AUX NORMES COMPTABLES", 28),
            h("2.1.1. Incidence de l'application", 28),
            h("3. PRÉSENTATION ET PRINCIPES", 28),
            h("3.1. Etat du résultat global", 28),
            h("4. ENGAGEMENTS CONTRACTUELS", 39),
            h("NOTE 7. ACTIFS FINANCIERS NON COURANTS", 47),
            h("7.1 Titres de participations non consolidés", 48),
            h("NOTE 34. IFRS 16 AU 31 DÉCEMBRE 2025", 71),
            h("34.1 Droit d'utilisation", 71),
            h("4. COMPTES SOCIAUX DE MAROC TELECOM", 79),
        ]
    )
    assert tree(out) == [
        "3. COMPTES CONSOLIDÉS DU GROUPE",
        "  NOTE 1. PRINCIPES COMPTABLES",
        "    1. CONTEXTE DE L'ÉLABORATION",
        "    2. CONFORMITÉ AUX NORMES COMPTABLES",
        "      2.1.1. Incidence de l'application",
        "    3. PRÉSENTATION ET PRINCIPES",
        "      3.1. Etat du résultat global",
        "    4. ENGAGEMENTS CONTRACTUELS",
        "  NOTE 7. ACTIFS FINANCIERS NON COURANTS",
        "    7.1 Titres de participations non consolidés",
        "  NOTE 34. IFRS 16 AU 31 DÉCEMBRE 2025",
        "    34.1 Droit d'utilisation",
        "4. COMPTES SOCIAUX DE MAROC TELECOM",
    ]


def test_levels_match_tree_depth():
    out = build_outline([h("1. A"), h("1.1 B"), h("Tableau")])
    assert out[0].level == 1
    assert out[0].children[0].level == 2
    assert out[0].children[0].children[0].level == 3
