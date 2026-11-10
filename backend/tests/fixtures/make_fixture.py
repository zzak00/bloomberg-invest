"""Write `filing.pdf`: a two-page stand-in for an AMMC filing, for tests that need a real PDF.

The golden report is not redistributed, so tests use this. Run once and commit the result:

    uv run --with reportlab python tests/fixtures/make_fixture.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).with_name("filing.pdf")

RESULTS = [
    (
        "Le Groupe a réalisé en 2025 un chiffre d'affaires consolidé stable par rapport à 2024, "
        "porté par la croissance des activités mobiles en Afrique et par la hausse de l'Internet "
        "fixe au Maroc, qui compensent la baisse des services de voix."
    ),
    (
        "Le résultat opérationnel avant amortissements progresse grâce à la maîtrise des coûts "
        "d'exploitation et à la baisse des charges d'interconnexion, malgré la hausse des taxes "
        "sectorielles dans plusieurs filiales."
    ),
    (
        "Le résultat net ajusté part du Groupe s'établit en hausse, et le flux de trésorerie "
        "opérationnel reste élevé après un programme d'investissement soutenu dans les réseaux."
    ),
]
FIGURES = [
    (
        "Les chiffres clés du Groupe sont présentés ci-dessous en millions de dirhams, selon les "
        "normes IFRS, pour les exercices clos au 31 décembre 2024 et au 31 décembre 2025."
    ),
    (
        "Les montants des exercices précédents n'ont pas été retraités. Les variations à base "
        "comparable tiennent compte des effets de change et des changements de périmètre."
    ),
]
OVERVIEW = [
    (
        "Le Groupe opère au Maroc et dans dix pays d'Afrique, où il fournit des services de "
        "téléphonie mobile, d'Internet fixe et mobile, de télévision et de paiement mobile."
    ),
    (
        "Au Maroc, le parc mobile progresse grâce aux offres prépayées et à la montée en débit "
        "des réseaux, tandis que le parc fixe bénéficie du déploiement de la fibre optique."
    ),
    (
        "À l'international, les filiales poursuivent la modernisation de leurs réseaux et le "
        "développement des services de paiement mobile, qui contribuent à la croissance."
    ),
    (
        "Le Groupe maintient une politique de distribution de dividendes régulière, adaptée à "
        "ses besoins d'investissement et à son niveau d'endettement. Au titre de l'exercice "
        "2025, le Conseil propose un dividende de 4,01 dirhams par action."
    ),
]


def main() -> None:
    styles = getSampleStyleSheet()
    table = Table(
        [
            ["(En millions MAD)", "31-déc.-24", "31-déc.-25"],
            ["Chiffre d'affaires", "36 699", "36 681"],
            ["Résultat net", "6 968", "7 112"],
        ]
    )
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    body = styles["BodyText"]
    # Dense body text, like a real filing: on a near-empty page Docling's layout model labels
    # headings differently from one platform to another.
    story = [
        Paragraph("1. RÉSULTATS CONSOLIDÉS", styles["Heading1"]),
        *[Paragraph(text, body) for text in RESULTS],
        Paragraph("1.1 Chiffres consolidés en dirham", styles["Heading2"]),
        *[Paragraph(text, body) for text in FIGURES],
        Spacer(1, 12),
        table,
        PageBreak(),
        Paragraph("2. VUE D'ENSEMBLE", styles["Heading1"]),
        *[Paragraph(text, body) for text in OVERVIEW],
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Filing fixture").build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
