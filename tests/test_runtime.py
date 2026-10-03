from pathlib import Path

import pytest

from activlayer import ApprovalPolicy, PermissionDenied, RunStatus, Runtime, Step, Worker, tool


@tool(permission="records.read")
def normalize(value: str) -> str:
    return value.strip().upper()


@tool(permission="records.write", approval=ApprovalPolicy.REQUIRED)
def commit(value: str) -> dict:
    return {"committed": value}


def build_worker() -> Worker:
    return Worker(
        name="record-processor",
        steps=(
            Step("normalize", normalize, lambda state: {"value": state["input"]["value"]}),
            Step("commit", commit, lambda state: {"value": state["outputs"]["normalize"]}),
        ),
    )


def test_run_pauses_for_approval_and_resumes(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path / "runtime.db")
    run = runtime.start(
        build_worker(), {"value": "  hello  "}, permissions={"records.read", "records.write"}
    )
    assert run.status == RunStatus.WAITING_APPROVAL
    assert run.state["outputs"]["normalize"] == "HELLO"

    run = runtime.approve(run.id, actor="reviewer", reason="Looks good")
    assert run.status == RunStatus.SUCCEEDED
    assert run.state["outputs"]["commit"] == {"committed": "HELLO"}
    assert runtime.store.verify_events(run.id)


def test_permission_is_enforced(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path / "runtime.db")
    with pytest.raises(PermissionDenied):
        runtime.start(build_worker(), {"value": "hello"}, permissions={"records.read"})


def test_completed_run_is_idempotent(tmp_path: Path) -> None:
    runtime = Runtime(tmp_path / "runtime.db")
    run = runtime.start(
        build_worker(), {"value": "hello"}, permissions={"records.read", "records.write"}
    )
    completed = runtime.approve(run.id, actor="reviewer")
    same = runtime.execute(run.id)
    assert same == completed

