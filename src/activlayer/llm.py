"""OpenAI-compatible LLM client for local and remote inference servers."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from .workspace import Workspace, WorkspaceError

PROVIDER_DEFAULTS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "vllm": "http://localhost:8000/v1",
    "llama-cpp": "http://localhost:8080/v1",
    "openai-compatible": "http://localhost:8000/v1",
}


class LLMError(RuntimeError):
    pass


@dataclass(slots=True)
class LLMResponse:
    content: str
    model: str
    usage: dict[str, Any]
    raw: dict[str, Any]

    def json(self) -> Any:
        text = self.content.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        return json.loads(text)


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        timeout: float = 120,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.headers = dict(headers or {})
        if api_key:
            self.headers["Authorization"] = f"Bearer {api_key}"

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if response_format is not None:
            body["response_format"] = response_format
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"].get("content") or ""
            return LLMResponse(
                content=content,
                model=payload.get("model", self.model),
                usage=payload.get("usage") or {},
                raw=payload,
            )
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise LLMError(f"LLM request failed: {error}") from error

    def models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.base_url}/models", headers=self.headers, timeout=10)
            response.raise_for_status()
            return [str(item["id"]) for item in response.json().get("data", [])]
        except (httpx.HTTPError, KeyError, ValueError) as error:
            raise LLMError(f"Provider check failed: {error}") from error


def client_from_workspace(
    workspace: Workspace, provider_name: str | None = None
) -> OpenAICompatibleClient:
    config = workspace.config
    name = provider_name or config.get("active_provider")
    if not name:
        raise WorkspaceError("No active LLM provider. Run `activlayer llm add` and `llm use`.")
    try:
        provider = config["providers"][name]
    except KeyError as error:
        raise WorkspaceError(f"Unknown LLM provider: {name}") from error
    api_key = workspace.resolve_secret(provider.get("api_key_env"))
    return OpenAICompatibleClient(
        base_url=provider["base_url"],
        model=provider["model"],
        api_key=api_key,
        timeout=float(provider.get("timeout_seconds", 120)),
        headers=provider.get("headers"),
    )
