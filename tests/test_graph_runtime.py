from pathlib import Path

import pytest

from activlayer.agent import AgentRepository
from activlayer.graph_runtime import GraphRuntime
from activlayer.runtime import PermissionDenied
from activlayer.spec import RunStatus
from activlayer.workspace import Workspace


def build_environment(tmp_path: Path) -> tuple[Workspace, dict]:
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example")
    repository = AgentRepository(workspace)
    agent = repository.create("Governed request", agent_id="governed-request")
    repository.add_node(
        agent["id"],
        "check",
        "rule.completeness",
        config={"required": ["request"]},
    )
    repository.add_node(
        agent["id"],
        "approve",
        "control.approval",
        config={"permission": "requests.approve", "approval_reason": "Review the request"},
    )
    repository.disconnect(agent["id"], "trigger-output")
    repository.connect(agent["id"], "trigger", "check")
    repository.connect(agent["id"], "check", "approve")
    repository.connect(agent["id"], "approve", "output")
    return workspace, repository.publish(agent["id"])


def test_graph_run_is_durable_and_approval_gated(tmp_path: Path) -> None:
    workspace, agent = build_environment(tmp_path)
    runtime = GraphRuntime(workspace)
    run = runtime.start(
        agent,
        {"request": "Ship the order"},
        permissions={"requests.approve"},
        actor="operator@example.com",
    )
    assert run.status == RunStatus.WAITING_APPROVAL
    assert run.current_step == 2
    assert runtime.store.get_run(run.id).status == RunStatus.WAITING_APPROVAL

    completed = runtime.approve(run.id, actor="reviewer@example.com", reason="Checked")
    assert completed.status == RunStatus.SUCCEEDED
    assert completed.state["outputs"]["check"]["passed"] is True
    assert runtime.store.verify_events(run.id)


def test_graph_permission_is_enforced(tmp_path: Path) -> None:
    workspace, agent = build_environment(tmp_path)
    with pytest.raises(PermissionDenied, match="requests.approve"):
        GraphRuntime(workspace).start(agent, {"request": "Ship"})


def test_failed_completeness_routes_to_review(tmp_path: Path) -> None:
    workspace, agent = build_environment(tmp_path)
    runtime = GraphRuntime(workspace)
    run = runtime.start(agent, {}, permissions={"requests.approve"})
    assert run.state["outputs"]["check"]["passed"] is False
    assert run.state["context"]["flags"]


def test_unsupported_studio_node_fails_prepublication_check(tmp_path: Path) -> None:
    workspace, agent = build_environment(tmp_path)
    agent["graph"]["nodes"][1]["type"] = "rule.specialized_private_check"
    errors = GraphRuntime(workspace).execution_errors(agent)
    assert "unsupported type" in errors[0]
