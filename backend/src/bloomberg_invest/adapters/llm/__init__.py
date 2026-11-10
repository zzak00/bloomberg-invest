"""The LLM interface: a system and a user message in, a JSON object matching a schema out.

Services never see the client library. Tests never call a live model: they replay recorded
responses (`recording.py`) or use a fake (#19 testing decisions).
"""

from typing import Any, Protocol


class LLM(Protocol):
    tool: str  # the service, as recorded on the Run
    tool_version: str  # the client library's version
    model: str  # the deployment or model name
    config: dict[str, str]  # what a Run records about the model

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        """The model's answer, a JSON object valid against the strict `schema`."""
