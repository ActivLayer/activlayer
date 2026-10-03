import json
from pathlib import Path

import pytest

from activlayer.agent import AgentRepository, AgentValidationError, new_agent, topological_order
from activlayer.workspace import MAX_USERS, Workspace, WorkspaceError


def workspace(tmp_path: Path) -> Workspace:
    return Workspace.initialize(
        tmp_path / ".activlayer", "Example Organization", owner_email="owner@example.com"
    )


def test_workspace_is_single_org_and_enforces_user_limit(tmp_path: Path) -> None:
    environment = workspace(tmp_path)
    users = environment.users
    for index in range(2):
        users.append(
            {
                "id": str(index),
                "email": f"user{index}@example.com",
                "name": f"User {index}",
                "role": "member",
                "active": True,
            }
        )
    environment.save_users(users)
    assert len(environment.users) == MAX_USERS

    users.append(
        {
            "id": "overflow",
            "email": "overflow@example.com",
            "name": "Overflow",
            "role": "member",
            "active": True,
        }
    )
    with pytest.raises(WorkspaceError, match="at most 3 users"):
        environment.save_users(users)


def test_agent_json_round_trip_and_node_editing(tmp_path: Path) -> None:
    repository = AgentRepository(workspace(tmp_path))
    agent = repository.create("Review request", agent_id="review-request")
    repository.add_node(
        agent["id"],
        "check",
        "rule.completeness",
        config={"required": ["request"]},
    )
    repository.disconnect(agent["id"], "trigger-output")
    repository.connect(agent["id"], "trigger", "check")
    repository.connect(agent["id"], "check", "output")
    repository.set_node(agent["id"], "check", "data.label", "Check request")

    updated = repository.load(agent["id"])
    assert topological_order(updated) == ["trigger", "check", "output"]
    assert repository.get_node(updated, "check")["data"]["label"] == "Check request"

    published = repository.publish(agent["id"])
    assert published["status"] == "published"
    assert published["version"] == "1"
    assert repository.load(agent["id"])["status"] == "draft"
    assert repository.load(agent["id"], published=True)["graph"] == published["graph"]

    export = tmp_path / "agent.json"
    export.write_text(json.dumps(published), encoding="utf-8")
    second = AgentRepository(Workspace.initialize(tmp_path / "second", "Second Organization"))
    imported = second.import_file(export)
    assert imported["id"] == agent["id"]


def test_cycle_is_rejected(tmp_path: Path) -> None:
    repository = AgentRepository(workspace(tmp_path))
    agent = new_agent("Cyclic")
    agent["graph"]["edges"].append(
        {"id": "output-trigger", "source": "output", "target": "trigger"}
    )
    with pytest.raises(AgentValidationError, match="cycle"):
        repository.save(agent)
