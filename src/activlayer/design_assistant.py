"""Safe natural-language planning for Agent Studio compatible definitions."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from .agent import AgentError, AgentRepository, new_agent, set_path, validate_agent
from .catalog import NODE_CATALOG
from .graph_runtime import GraphRuntime
from .llm import client_from_workspace
from .workspace import Workspace, slugify


class DesignAssistantError(AgentError):
    pass


class Planner(Protocol):
    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any: ...


ALLOWED_OPERATIONS = {
    "create_agent",
    "set_agent",
    "add_node",
    "set_node",
    "remove_node",
    "connect",
    "disconnect",
    "set_managed_workers",
}
PROTECTED_AGENT_PATHS = {"id", "status", "version", "created_at", "updated_at", "graph"}
MAX_OPERATIONS = 50


@dataclass(slots=True)
class DesignPlan:
    summary: str
    operations: list[dict[str, Any]]
    preview: dict[str, dict[str, Any]]


class DesignAssistant:
    """Translate a request into an allowlisted, validated and reviewable change set."""

    def __init__(self, workspace: Workspace, planner: Planner | None = None) -> None:
        self.workspace = workspace
        self.repository = AgentRepository(workspace)
        self.planner = planner

    def plan(self, request: str, *, provider: str | None = None) -> DesignPlan:
        request = request.strip()
        if not request:
            raise DesignAssistantError("Design request cannot be empty")
        if len(request) > 12_000:
            raise DesignAssistantError("Design request is too long")
        client = self.planner or client_from_workspace(self.workspace, provider)
        response = client.chat(
            [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": request},
            ],
            temperature=0,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )
        try:
            payload = response.json()
        except (json.JSONDecodeError, AttributeError, TypeError) as error:
            raise DesignAssistantError("The design model did not return valid JSON") from error
        return self.validate_plan(payload)

    def validate_plan(self, payload: Any) -> DesignPlan:
        if not isinstance(payload, dict):
            raise DesignAssistantError("Design plan must be a JSON object")
        operations = payload.get("operations")
        if not isinstance(operations, list) or not operations:
            raise DesignAssistantError("Design plan requires a non-empty operations array")
        if len(operations) > MAX_OPERATIONS:
            raise DesignAssistantError(f"Design plan exceeds {MAX_OPERATIONS} operations")
        staged = self._current_drafts()
        for index, operation in enumerate(operations, start=1):
            if not isinstance(operation, dict):
                raise DesignAssistantError(f"Operation {index} must be an object")
            kind = operation.get("op")
            if kind not in ALLOWED_OPERATIONS:
                raise DesignAssistantError(f"Operation {index} is not allowed: {kind}")
            try:
                self._stage(staged, operation)
            except (AgentError, KeyError, TypeError, ValueError) as error:
                raise DesignAssistantError(f"Operation {index} is invalid: {error}") from error
        self._validate_staged(staged)
        return DesignPlan(
            summary=str(payload.get("summary") or "Update agent design"),
            operations=copy.deepcopy(operations),
            preview=staged,
        )

    def apply(self, plan: DesignPlan) -> Path:
        # Revalidate immediately before writing to prevent applying a mutated plan.
        validated = self.validate_plan({"summary": plan.summary, "operations": plan.operations})
        changed_ids = sorted(
            {
                slugify(str(operation.get("agent_id") or operation.get("id")))
                for operation in validated.operations
            }
        )
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        backup = self.workspace.root / "backups" / timestamp
        backup.mkdir(parents=True, exist_ok=False)
        for agent_id in changed_ids:
            current = self.workspace.draft_path(agent_id)
            if current.exists():
                (backup / current.name).write_bytes(current.read_bytes())
        for agent_id in changed_ids:
            self.repository.save(validated.preview[agent_id])
        transcript = self.workspace.root / "design-chat.jsonl"
        with transcript.open("a", encoding="utf-8") as stream:
            stream.write(
                json.dumps(
                    {
                        "time": datetime.now(UTC).isoformat(),
                        "summary": validated.summary,
                        "operations": validated.operations,
                        "backup": str(backup),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
        return backup

    def _current_drafts(self) -> dict[str, dict[str, Any]]:
        return {
            agent["id"]: {key: value for key, value in agent.items() if key != "_source"}
            for agent in self.repository.list(published=False)
        }

    def _agent(
        self, staged: dict[str, dict[str, Any]], operation: dict[str, Any]
    ) -> dict[str, Any]:
        agent_id = slugify(str(operation.get("agent_id", "")))
        if agent_id not in staged:
            raise AgentError(f"Unknown draft agent: {agent_id}")
        return staged[agent_id]

    def _stage(self, staged: dict[str, dict[str, Any]], operation: dict[str, Any]) -> None:
        kind = operation["op"]
        if kind == "create_agent":
            agent_id = slugify(str(operation.get("id") or operation.get("name", "")))
            if agent_id in staged or self.workspace.published_path(agent_id).exists():
                raise AgentError(f"Agent already exists: {agent_id}")
            staged[agent_id] = new_agent(
                str(operation.get("name") or agent_id),
                agent_id=agent_id,
                description=str(operation.get("description", "")),
                agent_type=str(operation.get("agent_type", "worker")),
            )
            return
        agent = self._agent(staged, operation)
        if kind == "set_agent":
            path = str(operation.get("path", ""))
            root = path.split(".", 1)[0]
            if root in PROTECTED_AGENT_PATHS or not path:
                raise AgentError(f"Protected agent property: {path}")
            set_path(agent, path, copy.deepcopy(operation.get("value")))
        elif kind == "set_managed_workers":
            workers = operation.get("workers")
            if not isinstance(workers, list):
                raise AgentError("workers must be an array")
            agent["managed_workers"] = copy.deepcopy(workers)
        elif kind == "add_node":
            node_id = slugify(str(operation.get("node_id", "")))
            if any(node.get("id") == node_id for node in agent["graph"]["nodes"]):
                raise AgentError(f"Node already exists: {node_id}")
            node_type = str(operation.get("node_type", ""))
            if not node_type:
                raise AgentError("node_type is required")
            agent["graph"]["nodes"].append(
                {
                    "id": node_id,
                    "type": node_type,
                    "data": {
                        "label": str(operation.get("label") or node_id),
                        "subtitle": "",
                        "config": copy.deepcopy(operation.get("config") or {}),
                    },
                }
            )
        elif kind == "set_node":
            node = self._find_node(agent, str(operation.get("node_id", "")))
            path = str(operation.get("path", ""))
            if path == "id" or not path:
                raise AgentError(f"Protected node property: {path}")
            set_path(node, path, copy.deepcopy(operation.get("value")))
        elif kind == "remove_node":
            node_id = str(operation.get("node_id", ""))
            self._find_node(agent, node_id)
            agent["graph"]["nodes"] = [n for n in agent["graph"]["nodes"] if n["id"] != node_id]
            agent["graph"]["edges"] = [
                edge
                for edge in agent["graph"]["edges"]
                if edge.get("source") != node_id and edge.get("target") != node_id
            ]
        elif kind == "connect":
            source, target = str(operation.get("source", "")), str(operation.get("target", ""))
            self._find_node(agent, source)
            self._find_node(agent, target)
            edge_id = slugify(str(operation.get("edge_id") or f"{source}-{target}"))
            if any(edge.get("id") == edge_id for edge in agent["graph"]["edges"]):
                raise AgentError(f"Edge already exists: {edge_id}")
            agent["graph"]["edges"].append({"id": edge_id, "source": source, "target": target})
        elif kind == "disconnect":
            edge_id = str(operation.get("edge_id", ""))
            original = len(agent["graph"]["edges"])
            agent["graph"]["edges"] = [e for e in agent["graph"]["edges"] if e.get("id") != edge_id]
            if len(agent["graph"]["edges"]) == original:
                raise AgentError(f"Unknown edge: {edge_id}")

    @staticmethod
    def _find_node(agent: dict[str, Any], node_id: str) -> dict[str, Any]:
        for node in agent["graph"]["nodes"]:
            if node.get("id") == node_id:
                return node
        raise AgentError(f"Unknown node: {node_id}")

    def _validate_staged(self, staged: dict[str, dict[str, Any]]) -> None:
        runtime = GraphRuntime(self.workspace)
        errors: list[str] = []
        for agent_id, agent in staged.items():
            for error in [*validate_agent(agent), *runtime.execution_errors(agent)]:
                errors.append(f"{agent_id}: {error}")
            if agent.get("agent_type", "worker") == "orchestrator":
                workers = agent.get("managed_workers", [])
                if not workers:
                    errors.append(f"{agent_id}: An orchestrator must manage at least one worker")
                for worker_id in workers:
                    worker = staged.get(worker_id)
                    if worker is None:
                        try:
                            worker = self.repository.load(worker_id, published=True)
                        except AgentError:
                            errors.append(f"{agent_id}: Managed worker does not exist: {worker_id}")
                            continue
                    if worker.get("agent_type", "worker") != "worker":
                        errors.append(f"{agent_id}: Managed agent is not a worker: {worker_id}")
        if errors:
            raise DesignAssistantError("; ".join(errors))

    def _system_prompt(self) -> str:
        agents = [
            {
                "id": item["id"],
                "name": item["name"],
                "agent_type": item.get("agent_type", "worker"),
                "managed_workers": item.get("managed_workers", []),
                "nodes": [
                    {"id": node["id"], "type": node["type"]}
                    for node in item.get("graph", {}).get("nodes", [])
                ],
            }
            for item in self.repository.list(published=False)
        ]
        schema = {
            "summary": "short description",
            "operations": [
                {
                    "op": "one allowed operation",
                    "agent_id": "required except create_agent",
                    "other_fields": "fields required by that operation",
                }
            ],
        }
        return (
            "You are the ActivLayer design planner. Return only one JSON object. "
            "Translate the request into the smallest safe set of operations. Do not publish, "
            "delete agents, manage secrets, call tools, execute code, or invent operation names. "
            f"Allowed operations: {sorted(ALLOWED_OPERATIONS)}. "
            "create_agent fields: id, name, description, agent_type. set_agent fields: agent_id, "
            "path, value. set_managed_workers fields: agent_id, workers. "
            "add_node fields: agent_id, "
            "node_id, node_type, label, config. set_node fields: agent_id, node_id, path, value. "
            "remove_node fields: agent_id, node_id. connect fields: agent_id, source, target, "
            "edge_id. disconnect fields: agent_id, edge_id. Keep every graph acyclic with a "
            "trigger and output. "
            f"Output schema: {json.dumps(schema)}. Node catalog: {json.dumps(NODE_CATALOG)}. "
            f"Current draft agents: {json.dumps(agents)}"
        )
