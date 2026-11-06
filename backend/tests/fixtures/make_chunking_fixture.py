"""Write `chunking.pdf`: a stand-in filing with the cases the chunker must handle.

- "1. RÉSULTATS CONSOLIDÉS": body text that cites "note 2", then a table running onto page 2;
- "1.1 Faits marquants": numbered points;
- "2. VUE D'ENSEMBLE": a long section without sub-headings;
- "NOTE 2. DIVIDENDES": the proposed dividend.

Dense and spaced like a real filing, so Docling reads its headings and paragraphs the same on
every platform (see #21).
Run once and commit the result:

    uv run --with reportlab python tests/fixtures/make_chunking_fixture.py
"""

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUT = Path(__file__).with_name("chunking.pdf")

RESULTS = [
    (
        "Le Groupe a réalisé en 2025 un chiffre d'affaires consolidé stable par rapport à 2024, "
        "porté par la croissance des activités mobiles en Afrique et par la hausse de l'Internet "
        "fixe au Maroc, qui compensent la baisse des services de voix."
    ),
    (
        "Le résultat net ajusté part du Groupe progresse. Le Conseil propose un dividende en "
        "hausse, dont le détail figure en note 2 des comptes consolidés."
    ),
    (
        "Le tableau ci-dessous présente le chiffre d'affaires par filiale, en millions de "
        "dirhams, pour les exercices clos au 31 décembre 2024 et au 31 décembre 2025."
    ),
]
SUBSIDIARIES = [
    "Maroc",
    "Mauritel",
    "Onatel",
    "Gabon Telecom",
    "Sotelma",
    "Casanet",
    "Moov Africa Bénin",
    "Moov Africa Côte d'Ivoire",
    "Moov Africa Togo",
    "Moov Africa Niger",
    "Moov Africa Tchad",
    "Moov Africa Centrafrique",
    "MT Cash",
    "Uni Fiber",
    "Uni Tower",
]
POINTS = [
    (
        "1) Le déploiement de la fibre optique s'est accéléré au Maroc, avec plus de cent mille "
        "foyers raccordés au cours de l'exercice et une couverture étendue à de nouvelles villes."
    ),
    (
        "2) Les filiales africaines ont renouvelé plusieurs licences d'exploitation et étendu "
        "leurs réseaux 4G, ce qui soutient la croissance de l'Internet mobile."
    ),
    (
        "3) Le Groupe a poursuivi la maîtrise de ses coûts d'exploitation et la réduction de ses "
        "charges d'interconnexion, malgré la hausse des taxes sectorielles."
    ),
]
OVERVIEW = [
    (
        "Le Groupe opère au Maroc et dans dix pays d'Afrique, où il fournit des services de "
        "téléphonie mobile, d'Internet fixe et mobile, de télévision et de paiement mobile. "
        "Il s'appuie sur des réseaux modernisés et une distribution étendue."
    ),
    (
        "Au Maroc, le parc mobile progresse grâce aux offres prépayées et à la montée en débit "
        "des réseaux, tandis que le parc fixe bénéficie du déploiement de la fibre optique et "
        "de la hausse des usages de données."
    ),
    (
        "À l'international, les filiales poursuivent la modernisation de leurs réseaux et le "
        "développement des services de paiement mobile, qui contribuent à la croissance et à "
        "l'inclusion financière des populations."
    ),
    (
        "La concurrence reste vive sur l'ensemble des marchés, en particulier sur les offres "
        "de données mobiles, ce qui pèse sur les prix moyens malgré la hausse des volumes."
    ),
    (
        "Les investissements de l'exercice ont porté sur les réseaux d'accès, la fibre optique, "
        "les centres de données et les systèmes d'information, pour un montant en hausse."
    ),
    (
        "Le Groupe maintient une structure financière solide, avec un endettement maîtrisé et "
        "des flux de trésorerie opérationnels élevés qui financent ses investissements."
    ),
]
DIVIDEND = [
    (
        "Le dividende proposé à l'Assemblée générale au titre de l'exercice 2025 s'élève à "
        "4,40 dirhams par action, soit une distribution de 3 868 millions de dirhams."
    ),
    (
        "Il sera mis en paiement après l'approbation des comptes par l'Assemblée générale "
        "ordinaire, selon le calendrier publié par la société."
    ),
]


def main() -> None:
    styles = getSampleStyleSheet()
    # Justified, with a clear gap between paragraphs, as in a real filing: with BodyText's 6 pt
    # gap, Docling on Linux reads a section's paragraphs as one block.
    body = ParagraphStyle(
        "Body", parent=styles["BodyText"], alignment=TA_JUSTIFY, spaceBefore=0, spaceAfter=12
    )
    rows = [["Filiale", "31-déc.-24", "31-déc.-25"]] + [
        [name, f"{1000 + 37 * i:,}".replace(",", " "), f"{1010 + 41 * i:,}".replace(",", " ")]
        for i, name in enumerate(SUBSIDIARIES * 3)
    ]
    table = Table(rows, repeatRows=1)
    table.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey)]))
    story = [
        Paragraph("1. RÉSULTATS CONSOLIDÉS", styles["Heading1"]),
        *[Paragraph(text, body) for text in RESULTS * 2],
        Spacer(1, 12),
        table,
        Paragraph("1.1 Faits marquants", styles["Heading1"]),
        *[Paragraph(text, body) for text in POINTS],
        PageBreak(),
        Paragraph("2. VUE D'ENSEMBLE", styles["Heading1"]),
        *[Paragraph(text, body) for text in OVERVIEW * 2],
        Paragraph("NOTE 2. DIVIDENDES", styles["Heading1"]),
        *[Paragraph(text, body) for text in DIVIDEND],
    ]
    SimpleDocTemplate(str(OUT), pagesize=A4, title="Chunking fixture").build(story)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
