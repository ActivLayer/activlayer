from pathlib import Path

from fastapi.testclient import TestClient

from activlayer.agent import AgentRepository
from activlayer.api import create_app
from activlayer.workspace import Workspace


def test_authenticated_api_runs_published_agent(tmp_path: Path) -> None:
    workspace = Workspace.initialize(
        tmp_path / ".activlayer", "Example", owner_email="owner@example.com"
    )
    token = workspace.issue_token("owner@example.com")
    repository = AgentRepository(workspace)
    agent = repository.create("Echo", agent_id="echo")
    repository.publish(agent["id"])
    client = TestClient(create_app(workspace))

    assert client.get("/health").status_code == 200
    assert client.get("/v1/agents").status_code == 401

    headers = {"X-ActivLayer-Key": token}
    agents = client.get("/v1/agents", headers=headers)
    assert agents.status_code == 200
    assert agents.json()[0]["id"] == "echo"

    response = client.post(
        "/v1/runs",
        headers=headers,
        json={"agent_id": "echo", "input": {"message": "hello"}},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "succeeded"
