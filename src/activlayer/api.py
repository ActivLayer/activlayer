"""Authenticated HTTP API for a self-hosted Community Edition environment."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel, Field

from .agent import AgentError, AgentRepository, AgentValidationError
from .graph_runtime import GraphRuntime
from .runtime import ActivLayerError
from .workspace import Workspace


class StartRunRequest(BaseModel):
    agent_id: str
    input: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=list)
    draft: bool = False


class ApprovalRequest(BaseModel):
    reason: str = "Approved"


def _run_payload(run) -> dict[str, Any]:
    return {
        "id": run.id,
        "agent": run.worker,
        "version": run.worker_version,
        "status": run.status.value,
        "current_step": run.current_step,
        "error": run.error,
        "input": run.state.get("input"),
        "outputs": run.state.get("outputs"),
        "trace": run.state.get("trace"),
    }


def create_app(workspace: Workspace | None = None) -> FastAPI:
    workspace = workspace or Workspace.discover()
    repository = AgentRepository(workspace)
    runtime = GraphRuntime(workspace)
    application = FastAPI(
        title="ActivLayer Community Edition",
        version="0.3.3",
        description="Self-hosted API for governed orchestrators and Agent Workers.",
    )

    def current_user(x_activlayer_key: str | None = Header(default=None)) -> dict[str, Any]:
        if not x_activlayer_key:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing X-ActivLayer-Key")
        user = workspace.authenticate(x_activlayer_key)
        if user is None:
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid access key")
        return user

    @application.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "edition": "community"}

    @application.get("/v1/environment")
    def environment(user: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        config = workspace.config
        return {
            "organization": config["organization"],
            "active_provider": config.get("active_provider"),
            "user": {"email": user["email"], "name": user["name"], "role": user["role"]},
        }

    @application.get("/v1/agents")
    def agents(_: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        return [
            {
                "id": agent["id"],
                "name": agent["name"],
                "version": agent.get("version", "1"),
                "description": agent.get("description", ""),
                "agent_type": agent.get("agent_type", "worker"),
                "managed_workers": agent.get("managed_workers", []),
            }
            for agent in repository.list(published=True)
        ]

    @application.get("/v1/agents/{agent_id}")
    def agent(agent_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return repository.load(agent_id, published=True)
        except AgentError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @application.post("/v1/runs", status_code=status.HTTP_201_CREATED)
    def start_run(
        request: StartRunRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            definition = repository.load(request.agent_id, published=not request.draft)
            run = runtime.start(
                definition,
                request.input,
                permissions=set(request.permissions),
                actor=user["email"],
            )
            return _run_payload(run)
        except AgentValidationError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        except AgentError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ActivLayerError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @application.get("/v1/runs")
    def runs(
        limit: int = 50,
        _: dict[str, Any] = Depends(current_user),
    ) -> list[dict[str, Any]]:
        return [_run_payload(run) for run in runtime.store.list_runs(limit=min(limit, 200))]

    @application.get("/v1/runs/{run_id}")
    def run(run_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return _run_payload(runtime.store.get_run(run_id))
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @application.get("/v1/runs/{run_id}/events")
    def events(run_id: str, _: dict[str, Any] = Depends(current_user)) -> list[dict[str, Any]]:
        try:
            runtime.store.get_run(run_id)
            return runtime.store.events(run_id)
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error

    @application.post("/v1/runs/{run_id}/resume")
    def resume(run_id: str, _: dict[str, Any] = Depends(current_user)) -> dict[str, Any]:
        try:
            return _run_payload(runtime.execute(run_id))
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ActivLayerError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    @application.post("/v1/runs/{run_id}/approve")
    def approve(
        run_id: str,
        request: ApprovalRequest,
        user: dict[str, Any] = Depends(current_user),
    ) -> dict[str, Any]:
        try:
            return _run_payload(runtime.approve(run_id, actor=user["email"], reason=request.reason))
        except KeyError as error:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
        except ActivLayerError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    return application


app = None
