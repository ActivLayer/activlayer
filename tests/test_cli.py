from pathlib import Path

from typer.testing import CliRunner

from activlayer.cli import app

runner = CliRunner()


def invoke(home: Path, *arguments: str):
    return runner.invoke(app, ["--home", str(home), *arguments])


def test_cli_environment_and_agent_workflow(tmp_path: Path) -> None:
    home = tmp_path / ".activlayer"
    initialized = runner.invoke(
        app,
        [
            "init",
            "--organization",
            "Example Organization",
            "--owner",
            "owner@example.com",
            "--path",
            str(home),
        ],
    )
    assert initialized.exit_code == 0, initialized.output

    created = invoke(home, "agent", "new", "Request Worker", "--id", "request-worker")
    assert created.exit_code == 0, created.output
    added = invoke(
        home,
        "agent",
        "node",
        "add",
        "request-worker",
        "review",
        "--type",
        "control.approval",
    )
    assert added.exit_code == 0, added.output
    edited = invoke(
        home,
        "agent",
        "node",
        "set",
        "request-worker",
        "review",
        "data.config.approval_reason",
        "Operator review",
    )
    assert edited.exit_code == 0, edited.output
    shown = invoke(home, "agent", "node", "show", "request-worker", "review")
    assert shown.exit_code == 0
    assert "Operator review" in shown.output
    assert invoke(home, "agent", "publish", "request-worker").exit_code == 0


def test_cli_user_limit(tmp_path: Path) -> None:
    home = tmp_path / ".activlayer"
    runner.invoke(app, ["init", "--organization", "Example", "--path", str(home)])
    for index in range(3):
        result = invoke(home, "user", "add", f"user{index}@example.com")
        assert result.exit_code == 0
    overflow = invoke(home, "user", "add", "fourth@example.com")
    assert overflow.exit_code == 1
    assert "at most 3 users" in overflow.output


def test_cli_node_catalog_is_navigable() -> None:
    listed = runner.invoke(app, ["agent", "node", "types"])
    assert listed.exit_code == 0
    assert "control.approval" in listed.output
    explained = runner.invoke(app, ["agent", "node", "explain", "ai.prompt"])
    assert explained.exit_code == 0
    assert "OpenAI-compatible" in explained.output
