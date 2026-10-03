import json

import pytest

from activlayer.agent import AgentRepository
from activlayer.design_assistant import DesignAssistant, DesignAssistantError
from activlayer.workspace import Workspace


class Response:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload


class Planner:
    def __init__(self, payload):
        self.payload = payload

    def chat(self, messages, **kwargs):
        assert "Allowed operations" in messages[0]["content"]
        assert kwargs["temperature"] == 0
        return Response(self.payload)


def test_design_plan_is_staged_validated_and_applied(tmp_path):
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example Organization")
    repository = AgentRepository(workspace)
    repository.create("Worker One")
    payload = {
        "summary": "Create an orchestrator",
        "operations": [
            {
                "op": "create_agent",
                "id": "main-orchestrator",
                "name": "Main Orchestrator",
                "agent_type": "orchestrator",
            },
            {
                "op": "set_managed_workers",
                "agent_id": "main-orchestrator",
                "workers": ["worker-one"],
            },
        ],
    }
    assistant = DesignAssistant(workspace, Planner(payload))

    plan = assistant.plan("Create an orchestrator for Worker One")
    assert not workspace.draft_path("main-orchestrator").exists()
    backup = assistant.apply(plan)

    assert backup.exists()
    assert repository.load("main-orchestrator")["managed_workers"] == ["worker-one"]
    transcript = workspace.root / "design-chat.jsonl"
    assert json.loads(transcript.read_text().splitlines()[0])["summary"]


def test_design_assistant_rejects_unsafe_operations(tmp_path):
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example Organization")
    assistant = DesignAssistant(workspace)

    with pytest.raises(DesignAssistantError, match="not allowed"):
        assistant.validate_plan({"operations": [{"op": "run_shell", "command": "anything"}]})
