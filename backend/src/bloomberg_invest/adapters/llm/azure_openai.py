"""Azure OpenAI, the v1 LLM (#19 decisions, #10: `gpt-5.6-sol`), through its OpenAI-compatible
v1 endpoint. Needs the ingest extra; only `bootstrap` imports this module."""

import json
from importlib.metadata import version
from typing import Any

from openai import OpenAI

from bloomberg_invest.adapters.llm import LLM


class AzureOpenAILLM(LLM):
    tool = "azure-openai"

    def __init__(self, endpoint: str, api_key: str, deployment: str) -> None:
        self.model = deployment
        self.tool_version = version("openai")
        self.config = {"deployment": deployment, "api": "openai/v1"}
        # A page call takes about 20 s (#10); retries ride out rate limits and dropped connections.
        self._client = OpenAI(
            base_url=f"{endpoint.rstrip('/')}/openai/v1/",
            api_key=api_key,
            timeout=300,
            max_retries=5,
        )

    def complete_json(
        self, system: str, user: str, schema_name: str, schema: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": schema_name, "schema": schema, "strict": True},
            },
        )
        choice = response.choices[0]
        # A cut-off or refused answer is not valid JSON for the schema: fail the Run, never guess.
        if choice.finish_reason != "stop" or not choice.message.content:
            raise RuntimeError(f"{self.model} stopped with {choice.finish_reason!r}")
        return json.loads(choice.message.content)
