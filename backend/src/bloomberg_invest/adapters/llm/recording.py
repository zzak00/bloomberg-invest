"""Record a model's answers once, then replay them, so tests never call a live model (#19).

A recording is a JSON file holding the model's identity and its answers keyed by a SHA-256 of the
request (model, messages and schema). It holds no request text: the key is enough to replay.
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
    """Calls `inner` and adds each answer to the recording at `path`, kept across runs."""

    def __init__(self, inner: LLM, path: Path) -> None:
        self._inner, self._path = inner, path
        self.tool, self.tool_version = inner.tool, inner.tool_version
        self.model, self.config = inner.model, inner.config
        self._responses = _read(path)["responses"] if path.exists() else {}
        self._lock = threading.Lock()

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        answer = self._inner.complete_json(system, user, schema_name, schema)
        key = request_key(self.model, system, user, schema_name, schema)
        with self._lock:
            self._responses[key] = answer
            self._write()
        return answer

    def _write(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        recording = {
            "tool": self.tool,
            "tool_version": self.tool_version,
            "model": self.model,
            "config": self.config,
            "responses": self._responses,
        }
        self._path.write_text(json.dumps(recording, ensure_ascii=False, indent=1, sort_keys=True))


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


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())
