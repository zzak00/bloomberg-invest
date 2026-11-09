"""Running footers and page numbers Docling read as body text are dropped like its labelled ones."""

from bloomberg_invest.adapters.parsing.furniture import Furniture

# Docling's labelled footers on two pages: the running title, then a page number on its own.
# Boxes are (top, bottom) in PDF points from the top of an 842-point page.
FOOTERS = Furniture(
    [
        ("Maroc Telecom · Rapport financier 2025", 800.0, 807.0),
        ("10", 802.0, 809.0),
    ]
)


def test_the_running_footer_read_as_text_is_furniture_whatever_its_page_number():
    assert FOOTERS.covers("Maroc Telecom · Rapport financier 2025", 800.5, 807.0)
    assert FOOTERS.covers("90 Maroc Telecom · Rapport financier 2025", 800.0, 810.0)


def test_a_bare_page_number_in_the_footer_strip_is_furniture():
    assert FOOTERS.covers("6", 802.0, 809.0)


def test_the_same_text_away_from_the_strip_is_content():
    assert not FOOTERS.covers("Maroc Telecom · Rapport financier 2025", 120.0, 140.0)
    assert not FOOTERS.covers("1", 712.0, 785.0)


def test_other_text_in_the_strip_is_content():
    assert not FOOTERS.covers("Siège Social", 800.0, 808.0)


def test_with_no_labelled_furniture_nothing_is_dropped():
    assert not Furniture([]).covers("3", 802.0, 809.0)
