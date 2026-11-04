"""Rules the domain models enforce before anything reaches the graph (ADR 0003)."""

import pytest
from pydantic import ValidationError

from bloomberg_invest.domain.model import PageInfo, ParsedDocument, SectionNode


def test_a_section_must_sit_on_a_parsed_page():
    child = SectionNode(title="1.1 En dirham", level=2, page=9)
    with pytest.raises(ValidationError, match="1.1 En dirham.*page 9"):
        ParsedDocument(
            pages=[PageInfo(number=1, width=595, height=842)],
            sections=[SectionNode(title="1. RÉSULTATS", level=1, page=1, children=[child])],
        )
