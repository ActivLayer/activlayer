from pathlib import Path

import httpx

from activlayer.llm import OpenAICompatibleClient, client_from_workspace
from activlayer.workspace import Workspace


def test_openai_compatible_chat_and_models(monkeypatch) -> None:
    def fake_get(url, **kwargs):
        return httpx.Response(
            200,
            json={"data": [{"id": "local-model"}]},
            request=httpx.Request("GET", url),
        )

    def fake_post(url, **kwargs):
        assert url == "http://localhost:11434/v1/chat/completions"
        assert kwargs["json"]["model"] == "local-model"
        return httpx.Response(
            200,
            json={
                "model": "local-model",
                "choices": [{"message": {"content": '{"ready": true}'}}],
                "usage": {"total_tokens": 4},
            },
            request=httpx.Request("POST", url),
        )

    monkeypatch.setattr(httpx, "get", fake_get)
    monkeypatch.setattr(httpx, "post", fake_post)
    client = OpenAICompatibleClient(base_url="http://localhost:11434/v1", model="local-model")
    assert client.models() == ["local-model"]
    assert client.chat([{"role": "user", "content": "ready?"}]).json() == {"ready": True}


def test_workspace_provider_and_secret_resolution(tmp_path: Path) -> None:
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example")
    config = workspace.config
    config["providers"]["local"] = {
        "type": "ollama",
        "base_url": "http://localhost:11434/v1",
        "model": "local-model",
        "api_key_env": "LOCAL_MODEL_KEY",
    }
    config["active_provider"] = "local"
    workspace.save_config(config)
    workspace.set_secret("LOCAL_MODEL_KEY", "private-value")

    client = client_from_workspace(workspace)
    assert client.base_url == "http://localhost:11434/v1"
    assert client.headers["Authorization"] == "Bearer private-value"
