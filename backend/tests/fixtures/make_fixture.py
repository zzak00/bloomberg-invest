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
    story = [
        Paragraph("1. RÉSULTATS CONSOLIDÉS", styles["Heading1"]),
        Paragraph("1.1 Chiffres consolidés en dirham", styles["Heading2"]),
        Paragraph("Les chiffres clés du Groupe sont présentés ci-dessous.", styles["BodyText"]),
        Spacer(1, 12),
        table,
        PageBreak(),
        Paragraph("2. VUE D'ENSEMBLE", styles["Heading1"]),
        Paragraph("Le Groupe opère au Maroc et dans dix pays d'Afrique.", styles["BodyText"]),
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Filing fixture").build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
