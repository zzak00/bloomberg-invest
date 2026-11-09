"""Recording an LLM's answers once and replaying them (#19: no live calls in tests)."""

import json

import pytest
from fakes import PageReadingLLM

from bloomberg_invest.adapters.llm.recording import RecordingLLM, ReplayLLM

SCHEMA = {"type": "object", "properties": {"figures": {"type": "array"}}}
PAGE = 'Page 24\n\nParagraphs:\n\nTables:\n<table id="t24.0">\n<tr><td id="t24.0.r1.c2">36 681</td></tr>'


def test_a_recorded_answer_replays_without_the_model(tmp_path):
    path = tmp_path / "recording.json"
    live = PageReadingLLM({"36 681": {}})
    recorded = RecordingLLM(live, path).complete_json("system", PAGE, "figures", SCHEMA)

    replay = ReplayLLM(path)
    assert replay.complete_json("system", PAGE, "figures", SCHEMA) == recorded
    assert recorded["figures"][0]["source_id"] == "t24.0.r1.c2"
    assert (replay.tool, replay.model) == ("fake-llm", "fake-model")
    assert replay.config == {"deployment": "fake-model", "replayed": "true"}


def test_the_recording_keeps_answers_not_the_filing_s_text(tmp_path):
    path = tmp_path / "recording.json"
    RecordingLLM(PageReadingLLM({}), path).complete_json("system", PAGE, "figures", SCHEMA)
    assert "Page 24" not in path.read_text()
    assert len(json.loads(path.read_text())["responses"]) == 1


def test_recording_again_adds_to_the_same_file(tmp_path):
    path = tmp_path / "recording.json"
    RecordingLLM(PageReadingLLM({}), path).complete_json("system", "page 1", "figures", SCHEMA)
    RecordingLLM(PageReadingLLM({}), path).complete_json("system", "page 2", "figures", SCHEMA)
    assert len(json.loads(path.read_text())["responses"]) == 2


def test_a_request_never_recorded_fails_instead_of_calling_out(tmp_path):
    path = tmp_path / "recording.json"
    RecordingLLM(PageReadingLLM({}), path).complete_json("system", PAGE, "figures", SCHEMA)
    with pytest.raises(LookupError, match="record it again with LLM_RECORD"):
        ReplayLLM(path).complete_json("system", PAGE + " changed", "figures", SCHEMA)
