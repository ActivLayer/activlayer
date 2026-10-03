"""Public Agent Worker specification used by the Community runtime."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ApprovalPolicy(StrEnum):
    NEVER = "never"
    REQUIRED = "required"


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


ToolFunction = Callable[..., Any]
ArgumentFactory = Callable[[dict[str, Any]], Mapping[str, Any]]


@dataclass(frozen=True, slots=True)
class Tool:
    """A callable capability with an explicit permission and approval policy."""

    name: str
    function: ToolFunction
    description: str = ""
    permission: str | None = None
    approval: ApprovalPolicy = ApprovalPolicy.NEVER

    def __post_init__(self) -> None:
        if not self.name or any(char.isspace() for char in self.name):
            raise ValueError("Tool names must be non-empty and contain no whitespace")


def tool(
    name: str | None = None,
    *,
    description: str = "",
    permission: str | None = None,
    approval: ApprovalPolicy | str = ApprovalPolicy.NEVER,
) -> Callable[[ToolFunction], Tool]:
    """Turn a Python function into a governed ActivLayer tool."""

    def decorate(function: ToolFunction) -> Tool:
        return Tool(
            name=name or function.__name__,
            function=function,
            description=description or (function.__doc__ or "").strip(),
            permission=permission,
            approval=ApprovalPolicy(approval),
        )

    return decorate


@dataclass(frozen=True, slots=True)
class Step:
    """One durable step in a worker, with arguments derived from run state."""

    name: str
    tool: Tool
    arguments: ArgumentFactory = lambda state: state["input"]
    save_as: str | None = None
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least one")


@dataclass(frozen=True, slots=True)
class Worker:
    """A versioned, code-first definition of a governed Agent Worker."""

    name: str
    steps: tuple[Step, ...] | list[Step]
    description: str = ""
    version: str = "1"
    labels: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Worker name cannot be empty")
        if not self.steps:
            raise ValueError("Worker must define at least one step")
        names = [step.name for step in self.steps]
        if len(names) != len(set(names)):
            raise ValueError("Step names must be unique within a worker")


@dataclass(frozen=True, slots=True)
class Run:
    id: str
    worker: str
    worker_version: str
    status: RunStatus
    current_step: int
    state: dict[str, Any]
    permissions: frozenset[str]
    error: str | None = None
