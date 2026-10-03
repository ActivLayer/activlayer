"""Studio-compatible Agent Worker JSON model, validation, and editing."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .workspace import Workspace, slugify


class AgentError(RuntimeError):
    pass


class AgentValidationError(AgentError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


AGENT_TYPES = {"worker", "orchestrator"}


def new_agent(
    name: str,
    *,
    agent_id: str | None = None,
    description: str = "",
    agent_type: str = "worker",
) -> dict[str, Any]:
    if agent_type not in AGENT_TYPES:
        raise AgentError(f"Agent type must be one of: {', '.join(sorted(AGENT_TYPES))}")
    identifier = slugify(agent_id or name)
    if agent_type == "orchestrator":
        nodes = [
            {
                "id": "trigger",
                "type": "trigger.manual",
                "data": {"label": "Request", "subtitle": "CLI or API", "config": {}},
            },
            {
                "id": "route",
                "type": "orchestrator.route",
                "data": {"label": "Select worker", "subtitle": "Safe routing", "config": {}},
            },
            {
                "id": "delegate",
                "type": "orchestrator.delegate",
                "data": {"label": "Delegate", "subtitle": "Run selected worker", "config": {}},
            },
            {
                "id": "output",
                "type": "output.result",
                "data": {"label": "Result", "subtitle": "Worker response", "config": {}},
            },
        ]
        edges = [
            {"id": "trigger-route", "source": "trigger", "target": "route"},
            {"id": "route-delegate", "source": "route", "target": "delegate"},
            {"id": "delegate-output", "source": "delegate", "target": "output"},
        ]
    else:
        nodes = [
            {
                "id": "trigger",
                "type": "trigger.manual",
                "data": {"label": "Manual trigger", "subtitle": "CLI or API", "config": {}},
            },
            {
                "id": "output",
                "type": "output.result",
                "data": {"label": "Result", "subtitle": "Worker output", "config": {}},
            },
        ]
        edges = [{"id": "trigger-output", "source": "trigger", "target": "output"}]
    return {
        "schema_version": "1.0",
        "id": identifier,
        "name": name.strip(),
        "description": description,
        "agent_type": agent_type,
        "managed_workers": [],
        "memory": {
            "enabled": False,
            "auto_recall": True,
            "auto_remember": True,
            "scope_field": "customer_id",
            "recall_limit": 5,
        },
        "knowledge": {"collections": [], "top_k": 5},
        "domain": "general",
        "version": "1",
        "status": "draft",
        "trigger": "manual",
        "system_prompt": "You are a careful operational worker. Return accurate JSON.",
        "policy": {},
        "graph": {"nodes": nodes, "edges": edges},
        "created_at": datetime.now(UTC).isoformat(),
        "updated_at": datetime.now(UTC).isoformat(),
    }


def _node_ids(agent: dict[str, Any]) -> list[str]:
    return [str(node.get("id", "")) for node in agent.get("graph", {}).get("nodes", [])]


def topological_order(agent: dict[str, Any]) -> list[str]:
    nodes = _node_ids(agent)
    by_id = set(nodes)
    incoming = {node_id: 0 for node_id in nodes}
    outgoing: dict[str, list[str]] = {node_id: [] for node_id in nodes}
    for edge in agent.get("graph", {}).get("edges", []):
        source, target = edge.get("source"), edge.get("target")
        if source in by_id and target in by_id:
            incoming[target] += 1
            outgoing[source].append(target)
    ready = [node_id for node_id in nodes if incoming[node_id] == 0]
    ordered: list[str] = []
    while ready:
        node_id = ready.pop(0)
        ordered.append(node_id)
        for target in outgoing[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                ready.append(target)
    if len(ordered) != len(nodes):
        raise AgentValidationError(["Graph contains a cycle"])
    return ordered


def validate_agent(agent: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for field in ("id", "name", "graph"):
        if not agent.get(field):
            errors.append(f"Missing required agent property: {field}")
    graph = agent.get("graph")
    agent_type = agent.get("agent_type", "worker")
    if agent_type not in AGENT_TYPES:
        errors.append(f"agent_type must be one of: {', '.join(sorted(AGENT_TYPES))}")
    managed_workers = agent.get("managed_workers", [])
    if not isinstance(managed_workers, list) or any(
        not isinstance(worker, str) or not worker for worker in managed_workers
    ):
        errors.append("managed_workers must be an array of agent ids")
    elif len(managed_workers) != len(set(managed_workers)):
        errors.append("managed_workers cannot contain duplicates")
    if agent_type == "worker" and managed_workers:
        errors.append("A worker cannot manage other workers")
    memory = agent.get("memory")
    if memory is not None and not isinstance(memory, dict):
        errors.append("memory must be an object")
    elif isinstance(memory, dict):
        if not isinstance(memory.get("enabled", False), bool):
            errors.append("memory.enabled must be a boolean")
        if agent_type == "orchestrator" and memory.get("enabled", False):
            errors.append("Orchestrators cannot enable worker memory")
        if not isinstance(memory.get("scope_field", "customer_id"), str):
            errors.append("memory.scope_field must be a string")
        recall_limit = memory.get("recall_limit", 5)
        if not isinstance(recall_limit, int) or not 1 <= recall_limit <= 100:
            errors.append("memory.recall_limit must be between 1 and 100")
    knowledge = agent.get("knowledge")
    if knowledge is not None and not isinstance(knowledge, dict):
        errors.append("knowledge must be an object")
    elif isinstance(knowledge, dict):
        collections = knowledge.get("collections", [])
        if not isinstance(collections, list) or any(
            not isinstance(collection, str) or not collection for collection in collections
        ):
            errors.append("knowledge.collections must be an array of collection ids")
        top_k = knowledge.get("top_k", 5)
        if not isinstance(top_k, int) or not 1 <= top_k <= 100:
            errors.append("knowledge.top_k must be between 1 and 100")
    if not isinstance(graph, dict):
        return errors
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        errors.append("graph.nodes must be a non-empty array")
        nodes = []
    if not isinstance(edges, list):
        errors.append("graph.edges must be an array")
        edges = []
    ids = _node_ids(agent)
    if any(not value for value in ids):
        errors.append("Every node requires an id")
    if len(ids) != len(set(ids)):
        errors.append("Node ids must be unique")
    known = set(ids)
    for index, node in enumerate(nodes):
        if not node.get("type"):
            errors.append(f"Node {node.get('id') or index} requires a type")
        if not isinstance(node.get("data", {}), dict):
            errors.append(f"Node {node.get('id') or index} data must be an object")
        node_type = str(node.get("type", ""))
        if agent_type == "worker" and node_type.startswith("orchestrator."):
            errors.append(f"Worker node {node.get('id') or index} cannot orchestrate agents")
        if agent_type == "orchestrator" and node_type.startswith("memory."):
            errors.append(f"Orchestrator node {node.get('id') or index} cannot use worker memory")
    edge_ids: set[str] = set()
    for index, edge in enumerate(edges):
        edge_id = edge.get("id") or f"edge-{index}"
        if edge_id in edge_ids:
            errors.append(f"Duplicate edge id: {edge_id}")
        edge_ids.add(edge_id)
        if edge.get("source") not in known:
            errors.append(f"Edge {edge_id} has unknown source: {edge.get('source')}")
        if edge.get("target") not in known:
            errors.append(f"Edge {edge_id} has unknown target: {edge.get('target')}")
    triggers = [node for node in nodes if str(node.get("type", "")).startswith("trigger.")]
    outputs = [node for node in nodes if str(node.get("type", "")).startswith("output.")]
    if not triggers:
        errors.append("Agent requires at least one trigger node")
    if not outputs:
        errors.append("Agent requires at least one output node")
    if agent_type == "orchestrator" and not any(
        node.get("type") == "orchestrator.delegate" for node in nodes
    ):
        errors.append("An orchestrator requires an orchestrator.delegate node")
    if not errors:
        try:
            topological_order(agent)
        except AgentValidationError as error:
            errors.extend(error.errors)
    return errors


def parse_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [part for part in path.split(".") if part]
    if not parts:
        raise AgentError("Property path cannot be empty")
    current: dict[str, Any] = target
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise AgentError(f"Cannot descend into non-object property: {part}")
        current = child
    current[parts[-1]] = value


@dataclass(slots=True)
class AgentRepository:
    workspace: Workspace

    def list(self, *, published: bool | None = None) -> list[dict[str, Any]]:
        directories: list[tuple[Path, str]] = []
        if published is not True:
            directories.append((self.workspace.root / "agents" / "drafts", "draft"))
        if published is not False:
            directories.append((self.workspace.root / "agents" / "published", "published"))
        records: dict[str, dict[str, Any]] = {}
        for directory, source in directories:
            for path in sorted(directory.glob("*.json")):
                agent = json.loads(path.read_text(encoding="utf-8"))
                agent["_source"] = source
                records[f"{source}:{agent['id']}"] = agent
        return list(records.values())

    def load(self, agent_id: str, *, published: bool = False) -> dict[str, Any]:
        path = (
            self.workspace.published_path(agent_id)
            if published
            else self.workspace.draft_path(agent_id)
        )
        if not path.exists():
            kind = "published" if published else "draft"
            raise AgentError(f"No {kind} agent named '{agent_id}'")
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, agent: dict[str, Any], *, published: bool = False) -> Path:
        errors = validate_agent(agent)
        if errors:
            raise AgentValidationError(errors)
        agent = copy.deepcopy(agent)
        agent["updated_at"] = datetime.now(UTC).isoformat()
        path = (
            self.workspace.published_path(agent["id"])
            if published
            else self.workspace.draft_path(agent["id"])
        )
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(json.dumps(agent, indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def create(
        self,
        name: str,
        *,
        agent_id: str | None = None,
        description: str = "",
        agent_type: str = "worker",
    ) -> dict[str, Any]:
        agent = new_agent(
            name,
            agent_id=agent_id,
            description=description,
            agent_type=agent_type,
        )
        if self.workspace.draft_path(agent["id"]).exists():
            raise AgentError(f"Agent already exists: {agent['id']}")
        self.save(agent)
        return agent

    def relationship_errors(
        self, agent: dict[str, Any], *, published_required: bool = False
    ) -> list[str]:
        errors: list[str] = []
        if agent.get("agent_type", "worker") != "orchestrator":
            return errors
        workers = agent.get("managed_workers", [])
        if not workers:
            errors.append("An orchestrator must manage at least one worker")
        for worker_id in workers:
            if worker_id == agent.get("id"):
                errors.append("An orchestrator cannot manage itself")
                continue
            try:
                worker = self.load(worker_id, published=published_required)
            except AgentError:
                if published_required:
                    errors.append(f"Managed worker is not published: {worker_id}")
                    continue
                try:
                    worker = self.load(worker_id, published=True)
                except AgentError:
                    errors.append(f"Managed worker does not exist: {worker_id}")
                    continue
            if worker.get("agent_type", "worker") != "worker":
                errors.append(f"Managed agent is not a worker: {worker_id}")
        return errors

    def import_file(self, source: Path, *, replace: bool = False) -> dict[str, Any]:
        try:
            agent = json.loads(source.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise AgentError(f"Cannot read agent JSON: {error}") from error
        errors = validate_agent(agent)
        if errors:
            raise AgentValidationError(errors)
        target = self.workspace.draft_path(agent["id"])
        if target.exists() and not replace:
            raise AgentError(f"Draft already exists: {agent['id']}; use --replace")
        self.save(agent)
        return agent

    def publish(self, agent_id: str) -> dict[str, Any]:
        agent = self.load(agent_id)
        errors = validate_agent(agent)
        errors.extend(self.relationship_errors(agent, published_required=True))
        if errors:
            raise AgentValidationError(errors)
        published = copy.deepcopy(agent)
        published["status"] = "published"
        try:
            previous_path = self.workspace.published_path(agent_id)
            if previous_path.exists():
                previous = json.loads(previous_path.read_text(encoding="utf-8"))
                version = int(str(previous.get("version", "1"))) + 1
            else:
                version = max(1, int(str(agent.get("version", "1"))))
            published["version"] = str(version)
        except ValueError:
            pass
        self.save(published, published=True)
        agent["status"] = "draft"
        agent["version"] = published.get("version", agent.get("version", "1"))
        self.save(agent)
        return published

    def add_node(
        self,
        agent_id: str,
        node_id: str,
        node_type: str,
        *,
        label: str | None = None,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        agent = self.load(agent_id)
        if node_id in _node_ids(agent):
            raise AgentError(f"Node already exists: {node_id}")
        agent["graph"]["nodes"].append(
            {
                "id": node_id,
                "type": node_type,
                "data": {"label": label or node_id, "subtitle": "", "config": config or {}},
            }
        )
        self.save(agent)
        return agent

    def get_node(self, agent: dict[str, Any], node_id: str) -> dict[str, Any]:
        for node in agent["graph"]["nodes"]:
            if node["id"] == node_id:
                return node
        raise AgentError(f"Unknown node: {node_id}")

    def set_node(self, agent_id: str, node_id: str, path: str, value: Any) -> dict[str, Any]:
        agent = self.load(agent_id)
        node = self.get_node(agent, node_id)
        set_path(node, path, value)
        self.save(agent)
        return node

    def remove_node(self, agent_id: str, node_id: str) -> dict[str, Any]:
        agent = self.load(agent_id)
        self.get_node(agent, node_id)
        agent["graph"]["nodes"] = [
            node for node in agent["graph"]["nodes"] if node["id"] != node_id
        ]
        agent["graph"]["edges"] = [
            edge
            for edge in agent["graph"]["edges"]
            if edge.get("source") != node_id and edge.get("target") != node_id
        ]
        self.save(agent)
        return agent

    def connect(
        self, agent_id: str, source: str, target: str, *, edge_id: str | None = None
    ) -> dict[str, Any]:
        agent = self.load(agent_id)
        self.get_node(agent, source)
        self.get_node(agent, target)
        edge_id = edge_id or re.sub(r"[^a-zA-Z0-9_-]", "-", f"{source}-{target}")
        if any(edge.get("id") == edge_id for edge in agent["graph"]["edges"]):
            raise AgentError(f"Edge already exists: {edge_id}")
        agent["graph"]["edges"].append({"id": edge_id, "source": source, "target": target})
        self.save(agent)
        return agent

    def disconnect(self, agent_id: str, edge_id: str) -> dict[str, Any]:
        agent = self.load(agent_id)
        before = len(agent["graph"]["edges"])
        agent["graph"]["edges"] = [
            edge for edge in agent["graph"]["edges"] if edge.get("id") != edge_id
        ]
        if len(agent["graph"]["edges"]) == before:
            raise AgentError(f"Unknown edge: {edge_id}")
        self.save(agent)
        return agent
