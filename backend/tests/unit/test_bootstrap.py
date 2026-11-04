"""The composition root picks implementations from settings."""

from pathlib import Path

import pytest

from bloomberg_invest import bootstrap
from bloomberg_invest.settings import Settings


def test_an_unknown_parser_fails_naming_the_valid_choices():
    settings = Settings(
        neo4j_uri="", neo4j_user="", neo4j_password="", data_dir=Path("."), parser="nope"
    )
    with pytest.raises(ValueError, match="unknown parser 'nope', expected docling"):
        bootstrap.parser(settings)
