"""The Parser contract, run on every implementation in `bootstrap.PARSERS`, on the fixture PDF.

Needs the ingest extra. Docling-specific checks are at the end.
"""

from pathlib import Path

import pytest
from conftest import FIXTURES

pytestmark = pytest.mark.ingest
pytest.importorskip("docling", reason="needs the ingest extra")

from bloomberg_invest import bootstrap
from bloomberg_invest.adapters.parsing import Parser
from bloomberg_invest.domain.model import ParsedDocument
from bloomberg_invest.settings import Settings


def make_parser(name: str) -> Parser:
    settings = Settings(
        neo4j_uri="", neo4j_user="", neo4j_password="", data_dir=Path("."), parser=name
    )
    return bootstrap.parser(settings)


@pytest.fixture(scope="module", params=sorted(bootstrap.PARSERS))
def parser(request) -> Parser:
    return make_parser(request.param)


@pytest.fixture(scope="module")
def output(parser, tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("parses") / f"filing.{parser.tool}.json"


@pytest.fixture(scope="module")
def parsed(parser, output) -> ParsedDocument:
    return parser.parse(FIXTURES / "filing.pdf", output)


def test_the_tool_s_full_output_is_saved_for_later_steps(parsed, output):
    assert output.stat().st_size > 0


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


def test_the_parser_names_its_tool_version_and_configuration(parser):
    assert parser.tool and parser.tool_version and parser.config


def test_docling_saves_a_docling_document(parser, parsed, output):
    if parser.tool != "docling":
        pytest.skip("Docling only")
    from docling_core.types.doc import DoclingDocument

    document = DoclingDocument.load_from_json(output)
    assert sorted(document.pages) == [1, 2]
    assert any("VUE D'ENSEMBLE" in item.text for item in document.texts)


def test_docling_records_its_version_and_table_settings():
    parser = make_parser("docling")
    assert parser.tool == "docling"
    assert parser.tool_version == "2.145.0"
    assert parser.config == {
        "table_structure": "TableFormer v1",
        "mode": "accurate",
        "do_cell_matching": "true",
    }
