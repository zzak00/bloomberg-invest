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


def test_an_unknown_embedder_fails_naming_the_valid_choices():
    settings = Settings(
        neo4j_uri="", neo4j_user="", neo4j_password="", data_dir=Path("."), embedder="nope"
    )
    with pytest.raises(ValueError, match="unknown embedder 'nope', expected qwen3-0.6b"):
        bootstrap.embedder(settings)


def settings_for(**changes) -> Settings:
    return Settings(neo4j_uri="", neo4j_user="", neo4j_password="", data_dir=Path("."), **changes)


def test_an_unknown_llm_fails_naming_the_valid_choices():
    with pytest.raises(ValueError, match="unknown llm 'nope', expected azure-openai"):
        bootstrap.llm(settings_for(llm="nope"))


def test_extracting_without_the_azure_secrets_fails_naming_them():
    with pytest.raises(ValueError, match="AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_API_KEY"):
        bootstrap.llm(settings_for())
    with pytest.raises(ValueError, match="needs AZURE_OPENAI_API_KEY in"):
        bootstrap.llm(settings_for(azure_openai_endpoint="https://example.openai.azure.com"))


def test_a_replay_answers_from_its_recording_without_secrets(tmp_path):
    recording = tmp_path / "recording.jsonl"
    # A recording's first line names the model; no answers follow here.
    recording.write_text(
        '{"tool": "azure-openai", "tool_version": "3.46.0", "model": "gpt-5.6-sol",'
        ' "config": {"deployment": "gpt-5.6-sol"}}\n'
    )
    llm = bootstrap.llm(settings_for(llm_replay=recording))
    assert (llm.tool, llm.model) == ("azure-openai", "gpt-5.6-sol")
    assert llm.config == {"deployment": "gpt-5.6-sol", "replayed": "true"}
