"""Finding a quoted value in a stored filing's text layer, so the viewer highlights the quote
and not its whole paragraph (#19 R19)."""

import hashlib
import shutil

import pytest
from conftest import FIXTURES

from bloomberg_invest.adapters.files import DocumentFiles

PDF = FIXTURES / "filing.pdf"
SHA = hashlib.sha256(PDF.read_bytes()).hexdigest()
PAGE_2 = (2, 0.0, 0.0, 595.0, 842.0)


@pytest.fixture
def files(tmp_path) -> DocumentFiles:
    files = DocumentFiles(tmp_path)
    files.pdf_path(SHA).parent.mkdir(parents=True)
    shutil.copy(PDF, files.pdf_path(SHA))
    return files


def test_a_quote_is_boxed_on_its_line_in_pdf_points_from_the_top_left(files):
    [boxes] = files.quote_boxes(SHA, [(2, "4,01", (PAGE_2,))])

    assert boxes is not None and len(boxes) == 1
    page, left, top, right, bottom = boxes[0]
    assert page == 2
    assert (round(left), round(right)) == (138, 155)
    assert 215 < top < bottom < 235  # near the top of the page, not near its bottom
    assert bottom - top < 12  # one line, not the paragraph


def test_a_quote_outside_its_paragraph_or_not_on_the_page_is_not_found(files):
    elsewhere = (2, 0.0, 600.0, 595.0, 842.0)
    assert files.quote_boxes(SHA, [(2, "4,01", (elsewhere,)), (2, "9,99", (PAGE_2,))]) == [
        None,
        None,
    ]


def test_a_quote_inside_a_longer_number_is_not_found(files):
    page_1 = (1, 0.0, 0.0, 595.0, 842.0)
    inside, whole = files.quote_boxes(SHA, [(1, "68", (page_1,)), (1, "36 681", (page_1,))])
    assert inside is None  # in "36 681" and "6 968", never on its own
    assert whole is not None


def test_a_quote_near_nothing_is_the_first_place_the_page_holds_it(files):
    [expected] = files.quote_boxes(SHA, [(2, "4,01", (PAGE_2,))])
    assert files.quote_near(SHA, 2, "4,01", []) == expected
    assert files.quote_near(SHA, 2, "9,99", []) is None


def test_a_number_written_twice_is_boxed_where_it_was_picked(files):
    # Page 1: "... au 31 décembre 2024 et au 31 décembre 2025." holds "31" twice on one line.
    paragraph = (1, 50.0, 255.0, 545.0, 285.0)
    first = files.quote_near(SHA, 1, "31", [paragraph], occurrence=0)
    second = files.quote_near(SHA, 1, "31", [paragraph], occurrence=1)
    assert first is not None and second is not None
    assert first[0][2] == second[0][2]  # one line
    assert first[0][1] < second[0][1]  # the second is further right


def test_a_picked_occurrence_the_paragraph_does_not_hold_is_refused(files):
    paragraph = (1, 50.0, 255.0, 545.0, 285.0)  # holds "31" twice
    assert files.quote_near(SHA, 1, "31", [paragraph], occurrence=2) is None
    # A number written once may be found just outside the boxes: the nearest place.
    elsewhere = (1, 50.0, 300.0, 545.0, 340.0)
    assert files.quote_near(SHA, 1, "2025", [elsewhere]) is not None
