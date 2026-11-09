"""Record a model's answers once, then replay them, so tests never call a live model (#19).

A recording is a JSON Lines file: a first line naming the model, then one line per answer keyed
by a SHA-256 of the request (model, messages and schema). It holds no request text: the key is
enough to replay. Recording appends a line per answer, so a long run never rewrites the file.
"""

import hashlib
import json
import threading
from pathlib import Path
from typing import Any

from bloomberg_invest.adapters.llm import LLM


def request_key(model: str, system: str, user: str, schema_name: str, schema: dict) -> str:
    request = [model, system, user, schema_name, schema]
    return hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()


class RecordingLLM(LLM):
    """Calls `inner` and appends each answer to the recording at `path`, kept across runs."""

    def __init__(self, inner: LLM, path: Path) -> None:
        self._inner, self._path = inner, path
        self.tool, self.tool_version = inner.tool, inner.tool_version
        self.model, self.config = inner.model, inner.config
        self._lock = threading.Lock()
        if path.exists():
            recorded = _read(path)["model"]
            if recorded != self.model:
                raise ValueError(f"{path} records {recorded}, not {self.model}; record anew")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            header = {
                "tool": self.tool,
                "tool_version": self.tool_version,
                "model": self.model,
                "config": self.config,
            }
            path.write_text(_line(header))

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        answer = self._inner.complete_json(system, user, schema_name, schema)
        key = request_key(self.model, system, user, schema_name, schema)
        with self._lock, self._path.open("a") as handle:
            handle.write(_line({"key": key, "answer": answer}))
        return answer


class ReplayLLM(LLM):
    """Answers from a recording; a request it holds no answer for fails, never calls out."""

    def __init__(self, path: Path) -> None:
        recording = _read(path)
        self._path = path
        self.tool, self.tool_version = recording["tool"], recording["tool_version"]
        self.model = recording["model"]
        self.config = recording["config"] | {"replayed": "true"}
        self._responses = recording["responses"]

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        key = request_key(self.model, system, user, schema_name, schema)
        if key not in self._responses:
            raise LookupError(
                f"{self._path} holds no answer for this request (a changed prompt, label map or "
                "parse); record it again with LLM_RECORD"
            )
        return self._responses[key]


def _line(record: dict[str, Any]) -> str:
    return json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"


def _read(path: Path) -> dict[str, Any]:
    """The header with every answer under `responses`; a request answered twice keeps the last."""
    header, *answers = (json.loads(line) for line in path.read_text().splitlines() if line)
    return header | {"responses": {a["key"]: a["answer"] for a in answers}}
