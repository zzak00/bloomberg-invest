"""The Docling parser on the committed fixture PDF. Needs the ingest extra."""

import pytest
from conftest import FIXTURES

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest.parsing import docling_parser


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    return tmp_path_factory.mktemp("parses") / "filing.docling.json"


@pytest.fixture(scope="module")
def parsed(output):
    return docling_parser.DoclingParser().parse(FIXTURES / "filing.pdf", output)


def test_the_full_docling_output_is_saved_for_later_steps(parsed, output):
    from docling_core.types.doc import DoclingDocument

    document = DoclingDocument.load_from_json(output)
    assert sorted(document.pages) == [1, 2]
    assert any("VUE D'ENSEMBLE" in item.text for item in document.texts)


def test_every_page_has_its_size_in_points(parsed):
    assert [p.number for p in parsed.pages] == [1, 2]
    assert all(round(p.width) == 595 and round(p.height) == 842 for p in parsed.pages)


def test_headings_become_the_section_tree(parsed):
    [first, second] = parsed.sections
    assert first.title == "1. RÉSULTATS CONSOLIDÉS"
    assert [c.title for c in first.children] == ["1.1 Chiffres consolidés en dirham"]
    assert (second.title, second.page) == ("2. VUE D'ENSEMBLE", 2)


def test_section_boxes_are_top_left_points_inside_the_page(parsed):
    left, top, right, bottom = parsed.sections[0].bbox
    assert 0 <= left < right <= 595
    assert 0 <= top < bottom <= 842
    assert top < 200, "the first heading sits near the top of page 1"


def test_the_parser_names_its_tool_and_configuration():
    parser = docling_parser.DoclingParser()
    assert parser.tool == "docling"
    assert parser.tool_version == "2.145.0"
    assert parser.config == {
        "table_structure": "TableFormer v1",
        "mode": "accurate",
        "do_cell_matching": "true",
    }
