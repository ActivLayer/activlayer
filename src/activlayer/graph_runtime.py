"""Operational executor for Studio-compatible Agent Worker graphs."""

from __future__ import annotations

import json
import operator
import re
import time
import uuid
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any

import httpx

from .agent import AgentRepository, AgentValidationError, topological_order, validate_agent
from .knowledge import SharedKnowledge
from .llm import client_from_workspace
from .memory import AgentMemory
from .runtime import ActivLayerError, PermissionDenied
from .spec import Run, RunStatus
from .store import SQLiteStore
from .workspace import Workspace


class NodeExecutionError(ActivLayerError):
    pass


class UnsupportedNodeError(NodeExecutionError):
    pass


NodeHandler = Callable[[dict[str, Any], dict[str, Any]], Any]
_MISSING = object()


def resolve_path(data: Any, path: str, default: Any = None) -> Any:
    current = data
    for part in path.split("."):
        if isinstance(current, Mapping):
            current = current.get(part, _MISSING)
        elif isinstance(current, list) and part.isdigit():
            index = int(part)
            current = current[index] if index < len(current) else _MISSING
        else:
            current = _MISSING
        if current is _MISSING:
            return default
    return current


def _operand(value: str, context: dict[str, Any]) -> Any:
    value = value.strip()
    resolved = resolve_path(context, value, _MISSING)
    if resolved is not _MISSING:
        return resolved
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value.strip("'\"")


def evaluate(expression: str | None, context: dict[str, Any]) -> bool:
    """Evaluate the small, non-code expression language used in node conditions."""

    if not expression:
        return True
    expression = expression.strip()
    for joiner, aggregator in ((" or ", any), (" and ", all)):
        if joiner in expression:
            return aggregator(evaluate(part, context) for part in expression.split(joiner))
    if expression.startswith("not "):
        return not evaluate(expression[4:], context)
    match = re.fullmatch(r"(.+?)\s*(==|!=|>=|<=|>|<|in|contains)\s*(.+)", expression)
    if not match:
        return bool(resolve_path(context, expression))
    left, operation, right = match.groups()
    lhs, rhs = _operand(left, context), _operand(right, context)
    operations = {
        "==": operator.eq,
        "!=": operator.ne,
        ">=": operator.ge,
        "<=": operator.le,
        ">": operator.gt,
        "<": operator.lt,
        "in": lambda a, b: a in b,
        "contains": lambda a, b: b in a,
    }
    try:
        return bool(operations[operation](lhs, rhs))
    except (TypeError, ValueError):
        return False


def _render(template: str, context: dict[str, Any]) -> str:
    def replace_match(match: re.Match[str]) -> str:
        value = resolve_path(context, match.group(1).strip(), "")
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    return re.sub(r"\{([^{}]+)\}", replace_match, template)


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


class GraphRuntime:
    """Execute a validated agent graph with durable state and governance checks."""

    def __init__(self, workspace: Workspace) -> None:
        self.workspace = workspace
        self.store = SQLiteStore(workspace.state_path)
        self.handlers: dict[str, NodeHandler] = {}
        modules = workspace.config.get("extensions", [])
        if modules:
            from .extensions import load_extensions

            load_extensions(self, modules)

    def register_handler(self, node_type: str, handler: NodeHandler) -> None:
        self.handlers[node_type] = handler

    def execution_errors(self, agent: dict[str, Any]) -> list[str]:
        """Return fail-closed compatibility errors before a definition is published."""
        errors: list[str] = []
        built_in_rules = {
            "rule.ai",
            "rule.arithmetic",
            "rule.affordability",
            "rule.completeness",
            "rule.compute",
            "rule.condition",
            "rule.limit",
            "rule.membership",
            "rule.name_match",
        }
        for node in agent.get("graph", {}).get("nodes", []):
            node_id = node.get("id", "unknown")
            node_type = str(node.get("type", ""))
            config = node.get("data", {}).get("config", {})
            supported = (
                node_type in self.handlers
                or node_type.startswith("trigger.")
                or node_type.startswith("ai.")
                or node_type in built_in_rules
                or node_type == "control.approval"
                or node_type.startswith("decision.")
                or node_type.startswith("route.")
                or node_type.startswith("output.")
            )
            if node_type.startswith("rule.") and config.get("condition"):
                supported = True
            if node_type.startswith("integration.") or node_type == "tool.http":
                supported = True
                endpoint = str(config.get("endpoint") or config.get("url") or "")
                if not endpoint:
                    errors.append(f"Node '{node_id}' requires config.endpoint or config.url")
                if not endpoint.startswith(("http://", "https://")) and not config.get("connector"):
                    errors.append(
                        f"Node '{node_id}' has a relative endpoint and requires config.connector"
                    )
            if node_type == "function.call":
                name = config.get("function")
                supported = f"function:{name}" in self.handlers
            if node_type in {
                "orchestrator.route",
                "orchestrator.delegate",
                "knowledge.search",
                "memory.recall",
                "memory.remember",
            }:
                supported = True
            if node_type == "orchestrator.route":
                managed = set(agent.get("managed_workers", []))
                for route in config.get("routes", []):
                    if route.get("worker") not in managed:
                        errors.append(
                            f"Node '{node_id}' routes to an unmanaged worker: {route.get('worker')}"
                        )
                default_worker = config.get("default_worker")
                if default_worker and default_worker not in managed:
                    errors.append(
                        f"Node '{node_id}' defaults to an unmanaged worker: {default_worker}"
                    )
            if node_type == "orchestrator.delegate":
                fixed_worker = config.get("worker")
                if fixed_worker and fixed_worker not in agent.get("managed_workers", []):
                    errors.append(
                        f"Node '{node_id}' delegates to an unmanaged worker: {fixed_worker}"
                    )
            if not supported:
                errors.append(
                    f"Node '{node_id}' uses unsupported type '{node_type}'; install an extension"
                )
        return errors

    def start(
        self,
        agent: dict[str, Any],
        input: dict[str, Any],
        *,
        permissions: set[str] | frozenset[str] = frozenset(),
        actor: str | None = None,
        run_id: str | None = None,
        execute: bool = True,
    ) -> Run:
        errors = validate_agent(agent)
        errors.extend(
            AgentRepository(self.workspace).relationship_errors(agent, published_required=True)
        )
        errors.extend(self.execution_errors(agent))
        if errors:
            raise AgentValidationError(errors)
        order = topological_order(agent)
        context = dict(input)
        memory_config = agent.get("memory") or {}
        scope_field = str(memory_config.get("scope_field", "customer_id"))
        memory_scope = str(resolve_path(input, scope_field, "global"))
        if agent.get("agent_type", "worker") == "worker" and memory_config.get("enabled"):
            if memory_config.get("auto_recall", True):
                context["memory"] = AgentMemory(self.workspace, agent["id"]).recall(
                    memory_scope,
                    limit=int(memory_config.get("recall_limit", 5)),
                )
        knowledge_config = agent.get("knowledge") or {}
        collections = knowledge_config.get("collections") or []
        if collections:
            query = str(
                input.get("message")
                or input.get("request")
                or input.get("query")
                or json.dumps(input, ensure_ascii=False)
            )
            context["knowledge"] = SharedKnowledge(self.workspace).search(
                query,
                collections=collections,
                limit=int(knowledge_config.get("top_k", 5)),
            )
        actual_run_id = run_id or uuid.uuid4().hex
        run = Run(
            id=actual_run_id,
            worker=agent["id"],
            worker_version=str(agent.get("version", "1")),
            status=RunStatus.PENDING,
            current_step=0,
            state={
                "definition": agent,
                "run_id": actual_run_id,
                "order": order,
                "input": input,
                "outputs": {},
                "context": context,
                "trace": [],
                "attempts": {},
                "actor": actor,
                "permissions": sorted(permissions),
                "memory_scope": memory_scope,
                "started_at": datetime.now(UTC).isoformat(),
            },
            permissions=frozenset(permissions),
        )
        self.store.create_run(run)
        self.store.append_event(
            run.id,
            "run.created",
            {"agent": run.worker, "version": run.worker_version, "actor": actor},
        )
        return self.execute(run.id) if execute else run

    def execute(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        if run.status == RunStatus.SUCCEEDED:
            return run
        agent = run.state["definition"]
        nodes = {node["id"]: node for node in agent["graph"]["nodes"]}
        order: list[str] = run.state["order"]
        run = replace(run, status=RunStatus.RUNNING, error=None)
        self.store.save_run(run)

        while run.current_step < len(order):
            node = nodes[order[run.current_step]]
            node_id = node["id"]
            node_type = node["type"]
            data = node.get("data") or {}
            config = data.get("config") or {}

            if data.get("disabled") or not evaluate(config.get("when"), run.state["context"]):
                run = self._complete_node(run, node, "skipped", None)
                continue

            permission = config.get("permission")
            if permission and permission not in run.permissions:
                message = f"Node '{node_id}' requires permission '{permission}'"
                run = replace(run, status=RunStatus.FAILED, error=message)
                self.store.save_run(run)
                self.store.append_event(
                    run.id,
                    "permission.denied",
                    {"node": node_id, "permission": permission},
                )
                raise PermissionDenied(message)

            requires_approval = node_type == "control.approval" or bool(
                config.get("approval_required")
            )
            if requires_approval and not self.store.is_approved(run.id, node_id):
                run = replace(run, status=RunStatus.WAITING_APPROVAL)
                self.store.save_run(run)
                self.store.append_event(
                    run.id,
                    "approval.requested",
                    {
                        "node": node_id,
                        "label": data.get("label", node_id),
                        "reason": config.get("approval_reason", "Human review required"),
                    },
                )
                return run

            max_attempts = max(1, int(config.get("max_attempts", 3)))
            attempts = int(run.state["attempts"].get(node_id, 0))
            try:
                self.store.append_event(
                    run.id,
                    "node.started",
                    {"node": node_id, "type": node_type, "attempt": attempts + 1},
                )
                output = self._execute_node(node, run.state, agent)
                run.state["attempts"][node_id] = attempts + 1
                run = self._complete_node(run, node, "succeeded", _json_safe(output))
            except Exception as error:  # noqa: BLE001
                attempts += 1
                run.state["attempts"][node_id] = attempts
                self.store.append_event(
                    run.id,
                    "node.failed",
                    {"node": node_id, "type": node_type, "attempt": attempts, "error": str(error)},
                )
                if attempts >= max_attempts:
                    run.state["trace"].append(
                        {
                            "node": node_id,
                            "type": node_type,
                            "status": "failed",
                            "error": str(error),
                        }
                    )
                    run = replace(run, status=RunStatus.FAILED, error=str(error))
                    self.store.save_run(run)
                    return run
                self.store.save_run(run)
                time.sleep(min(0.1 * (2 ** (attempts - 1)), 1.0))

        memory_config = agent.get("memory") or {}
        if (
            agent.get("agent_type", "worker") == "worker"
            and memory_config.get("enabled")
            and memory_config.get("auto_remember", True)
        ):
            try:
                AgentMemory(self.workspace, agent["id"]).remember(
                    run.state.get("memory_scope", "global"),
                    {
                        "input": run.state["input"],
                        "output": run.state["outputs"].get(order[-1]),
                    },
                    run_id=run.id,
                )
            except Exception as error:  # noqa: BLE001
                message = f"Worker memory write failed: {error}"
                run = replace(run, status=RunStatus.FAILED, error=message)
                self.store.save_run(run)
                self.store.append_event(run.id, "memory.failed", {"error": str(error)})
                return run
        run.state["completed_at"] = datetime.now(UTC).isoformat()
        run = replace(run, status=RunStatus.SUCCEEDED)
        self.store.save_run(run)
        self.store.append_event(run.id, "run.succeeded", {"nodes": len(order)})
        return run

    def approve(self, run_id: str, *, actor: str, reason: str = "") -> Run:
        run = self.store.get_run(run_id)
        if run.status != RunStatus.WAITING_APPROVAL:
            raise ActivLayerError("Run is not waiting for approval")
        node_id = run.state["order"][run.current_step]
        self.store.approve(run.id, node_id, actor, reason)
        self.store.append_event(
            run.id,
            "approval.granted",
            {"node": node_id, "actor": actor, "reason": reason},
        )
        return self.execute(run.id)

    def _complete_node(self, run: Run, node: dict[str, Any], status: str, output: Any) -> Run:
        node_id = node["id"]
        if output is not None:
            run.state["outputs"][node_id] = output
            if isinstance(output, dict):
                run.state["context"].update(output)
            else:
                run.state["context"][node_id] = output
        run.state["trace"].append(
            {"node": node_id, "type": node["type"], "status": status, "output": output}
        )
        run = replace(run, current_step=run.current_step + 1)
        self.store.save_run(run)
        self.store.append_event(
            run.id,
            "node.completed",
            {"node": node_id, "type": node["type"], "status": status},
        )
        return run

    def _execute_node(
        self, node: dict[str, Any], state: dict[str, Any], agent: dict[str, Any]
    ) -> Any:
        node_type = node["type"]
        if node_type in self.handlers:
            return self.handlers[node_type](node, state)
        if node_type.startswith("trigger."):
            return state["input"]
        if node_type == "orchestrator.route":
            return self._execute_orchestrator_route(node, state, agent)
        if node_type == "orchestrator.delegate":
            return self._execute_orchestrator_delegate(node, state, agent)
        if node_type == "knowledge.search":
            return self._execute_knowledge(node, state, agent)
        if node_type == "memory.recall":
            return self._execute_memory_recall(node, state, agent)
        if node_type == "memory.remember":
            return self._execute_memory_remember(node, state, agent)
        if node_type.startswith("ai.") or node_type == "rule.ai":
            return self._execute_ai(node, state, agent)
        if node_type.startswith("rule."):
            return self._execute_rule(node, state)
        if node_type.startswith("integration.") or node_type == "tool.http":
            return self._execute_http(node, state)
        if node_type == "function.call":
            return self._execute_function(node, state)
        if node_type == "control.approval":
            return {"approved": True}
        if node_type.startswith("decision."):
            return self._execute_decision(node, state)
        if node_type.startswith("route."):
            return self._execute_route(node, state)
        if node_type.startswith("output."):
            return self._execute_output(node, state)
        raise UnsupportedNodeError(
            f"Unsupported node type '{node_type}'. Register a handler through the extension API."
        )

    def _execute_ai(
        self, node: dict[str, Any], state: dict[str, Any], agent: dict[str, Any]
    ) -> Any:
        config = node.get("data", {}).get("config", {})
        client = client_from_workspace(self.workspace, config.get("provider"))
        context = state["context"]
        instruction = config.get("prompt") or config.get("instruction")
        if not instruction:
            instruction = (
                f"Execute the {node['type']} operation named "
                f"{node.get('data', {}).get('label', node['id'])}. "
                "Return a JSON object with the useful result fields."
            )
        instruction = _render(str(instruction), context)
        user_payload = {
            "input": state["input"],
            "prior_results": state["outputs"],
            "context": state["context"],
            "node_configuration": config,
        }
        work_item = json.dumps(user_payload, ensure_ascii=False)
        response = client.chat(
            [
                {
                    "role": "system",
                    "content": str(agent.get("system_prompt") or "Return accurate JSON."),
                },
                {
                    "role": "user",
                    "content": f"{instruction}\n\nWORK ITEM:\n{work_item}",
                },
            ],
            temperature=float(config.get("temperature", 0)),
            max_tokens=int(config["max_tokens"]) if config.get("max_tokens") else None,
        )
        try:
            return response.json()
        except json.JSONDecodeError:
            return {"text": response.content, "model": response.model, "usage": response.usage}

    def _execute_rule(self, node: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        context = state["context"]
        node_type = node["type"]
        passed = True
        detail = "Rule passed"

        if node_type == "rule.completeness":
            missing = [
                field
                for field in config.get("required", [])
                if resolve_path(context, field) in (None, "", [])
            ]
            passed = not missing
            detail = "Complete" if passed else f"Missing: {', '.join(missing)}"
        elif node_type in {"rule.limit", "rule.arithmetic", "rule.affordability"}:
            left_path = config.get("field") or config.get("left") or "dti"
            left = resolve_path(context, left_path)
            right = config.get("max", config.get("right", config.get("max_dti")))
            if isinstance(right, str):
                right = resolve_path(context, right, right)
            operation = config.get("op", "<=")
            passed = evaluate(f"left {operation} right", {"left": left, "right": right})
            detail = f"{left_path}={left} {operation} {right}"
        elif node_type == "rule.membership":
            value = resolve_path(context, config.get("field", ""))
            passed = value in config.get("allowed", [])
            detail = f"value={value}; allowed={config.get('allowed', [])}"
        elif node_type == "rule.name_match":
            left = str(resolve_path(context, config.get("left", ""), "")).casefold()
            right = str(resolve_path(context, config.get("right", ""), "")).casefold()
            strategy = config.get("strategy", "exact")
            passed = left == right if strategy == "exact" else left in right or right in left
            detail = f"Compared {config.get('left')} with {config.get('right')}"
        elif node_type == "rule.compute":
            formula = str(config.get("formula", ""))
            match = re.fullmatch(r"([\w.]+)\s*([+\-*/])\s*([\w.]+)", formula)
            if not match:
                raise NodeExecutionError("rule.compute supports a two-operand arithmetic formula")
            left, symbol, right = match.groups()
            a, b = float(resolve_path(context, left, 0)), float(resolve_path(context, right, 0))
            operations = {
                "+": operator.add,
                "-": operator.sub,
                "*": operator.mul,
                "/": operator.truediv,
            }
            value = round(operations[symbol](a, b), int(config.get("round", 6)))
            return {str(config.get("target", node["id"])): value, "passed": True}
        elif config.get("condition"):
            passed = evaluate(str(config["condition"]), context)
            detail = str(config["condition"])
        else:
            message = f"Node type '{node_type}' needs an extension handler or config.condition"
            raise UnsupportedNodeError(message)

        result = {"passed": passed, "detail": detail}
        if not passed:
            state["context"].setdefault("flags", []).append(
                config.get("flag") or f"{node.get('data', {}).get('label', node['id'])}: {detail}"
            )
            result["outcome"] = config.get("on_breach", config.get("on_fail", "review"))
        return result

    def _execute_http(self, node: dict[str, Any], state: dict[str, Any]) -> Any:
        config = node.get("data", {}).get("config", {})
        workspace_config = self.workspace.config
        connector_name = config.get("connector")
        connector = (
            workspace_config.get("connectors", {}).get(connector_name, {}) if connector_name else {}
        )
        base_url = str(connector.get("base_url", "")).rstrip("/")
        endpoint = str(config.get("endpoint") or config.get("url") or "")
        if endpoint.startswith(("http://", "https://")):
            url = endpoint
        elif base_url and endpoint:
            url = f"{base_url}/{endpoint.lstrip('/')}"
        else:
            raise NodeExecutionError("HTTP node requires config.url or a connector plus endpoint")
        headers = dict(connector.get("headers") or {})
        secret_name = connector.get("api_key_env")
        secret = self.workspace.resolve_secret(secret_name)
        if secret:
            header_name = connector.get("auth_header", "Authorization")
            prefix = connector.get("auth_prefix", "Bearer ")
            headers[header_name] = f"{prefix}{secret}"
        body = config.get("body")
        if body is None:
            body = state["context"]
        elif isinstance(body, str):
            rendered = _render(body, state["context"])
            try:
                body = json.loads(rendered)
            except json.JSONDecodeError:
                body = {"value": rendered}
        try:
            response = httpx.request(
                str(config.get("method", "POST")).upper(),
                url,
                headers=headers,
                json=body,
                timeout=float(config.get("timeout_seconds", 30)),
            )
            response.raise_for_status()
            if not response.content:
                return {"status_code": response.status_code}
            try:
                return response.json()
            except ValueError:
                return {"status_code": response.status_code, "text": response.text}
        except httpx.HTTPError as error:
            raise NodeExecutionError(f"Integration request failed: {error}") from error

    def _execute_function(self, node: dict[str, Any], state: dict[str, Any]) -> Any:
        config = node.get("data", {}).get("config", {})
        name = config.get("function")
        handler = self.handlers.get(f"function:{name}")
        if handler is None:
            raise UnsupportedNodeError(f"Function '{name}' is not installed")
        return handler(node, state)

    def _execute_decision(self, node: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        flags = state["context"].get("flags", [])
        recommendation = (
            config.get("pass_label", "approve")
            if not flags
            else config.get("review_label", "review")
        )
        return {"recommendation": recommendation, "flags": flags}

    def _execute_route(self, node: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        return {
            "assigned_role": config.get("role", "Reviewer"),
            "reason": _render(str(config.get("reason", "Routed by policy")), state["context"]),
            "four_eyes": bool(config.get("four_eyes", False)),
        }

    def _execute_output(self, node: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        expose = config.get("expose")
        if expose:
            return {field: resolve_path(state["context"], field) for field in expose}
        return {
            "recommendation": state["context"].get("recommendation"),
            "flags": state["context"].get("flags", []),
            "selected_worker": state["context"].get("selected_worker"),
            "delegated_response": state["context"].get("delegated_response"),
            "results": deepcopy(state["outputs"]),
        }

    def _execute_orchestrator_route(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        if agent.get("agent_type") != "orchestrator":
            raise NodeExecutionError("orchestrator.route can only run inside an orchestrator")
        config = node.get("data", {}).get("config", {})
        managed = agent.get("managed_workers", [])
        if not managed:
            raise NodeExecutionError("Orchestrator has no managed workers")
        query = str(
            state["input"].get("message")
            or state["input"].get("request")
            or state["input"].get("query")
            or json.dumps(state["input"], ensure_ascii=False)
        ).casefold()
        selected: str | None = None
        reason = ""
        for route in config.get("routes", []):
            worker = route.get("worker")
            keywords = [str(value).casefold() for value in route.get("when_any", [])]
            if worker in managed and keywords and any(keyword in query for keyword in keywords):
                selected = worker
                reason = f"Matched route keywords for {worker}"
                break
        if selected is None and config.get("use_llm", False):
            repository = AgentRepository(self.workspace)
            candidates = []
            for worker_id in managed:
                worker = repository.load(worker_id, published=True)
                candidates.append(
                    {
                        "id": worker_id,
                        "name": worker.get("name"),
                        "description": worker.get("description", ""),
                    }
                )
            response = client_from_workspace(self.workspace, config.get("provider")).chat(
                [
                    {
                        "role": "system",
                        "content": (
                            "Select exactly one worker for the request. Return only JSON with "
                            "worker and reason. Never invent a worker id."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"request": state["input"], "workers": candidates},
                            ensure_ascii=False,
                        ),
                    },
                ],
                temperature=0,
                max_tokens=200,
            )
            try:
                choice = response.json()
            except json.JSONDecodeError as error:
                raise NodeExecutionError("Router model returned invalid JSON") from error
            proposed = choice.get("worker")
            if proposed not in managed:
                raise NodeExecutionError("Router model selected an unmanaged worker")
            selected = proposed
            reason = str(choice.get("reason", "Selected by model"))
        if selected is None:
            selected = config.get("default_worker") or managed[0]
            if selected not in managed:
                raise NodeExecutionError("Default worker is not managed by this orchestrator")
            reason = "Default route"
        return {"selected_worker": selected, "routing_reason": reason}

    def _execute_orchestrator_delegate(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        worker_id = config.get("worker") or resolve_path(
            state["context"], config.get("worker_from", "selected_worker")
        )
        if worker_id not in agent.get("managed_workers", []):
            raise NodeExecutionError(f"Cannot delegate to unmanaged worker: {worker_id}")
        worker = AgentRepository(self.workspace).load(str(worker_id), published=True)
        child_input = deepcopy(state["input"])
        child_input["orchestrator_id"] = agent["id"]
        child_input["parent_run_id"] = state.get("run_id")
        child = GraphRuntime(self.workspace).start(
            worker,
            child_input,
            permissions=set(state.get("permissions", [])),
            actor=state.get("actor"),
        )
        if child.status != RunStatus.SUCCEEDED:
            raise NodeExecutionError(
                f"Delegated worker {worker_id} stopped with status {child.status.value}; "
                f"child run {child.id}"
            )
        final_node = child.state["order"][-1]
        response = child.state["outputs"].get(final_node)
        return {
            "delegated_worker": worker_id,
            "delegated_run_id": child.id,
            "delegated_response": response,
        }

    def _execute_knowledge(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        query_template = str(config.get("query", "{request}"))
        query = _render(query_template, state["context"])
        collections = config.get("collections") or (agent.get("knowledge") or {}).get(
            "collections", []
        )
        results = SharedKnowledge(self.workspace).search(
            query,
            collections=collections,
            limit=int(config.get("top_k", 5)),
        )
        return {str(config.get("output_field", "knowledge")): results}

    def _execute_memory_recall(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        scope = str(
            resolve_path(
                state["context"],
                config.get("scope_field", "customer_id"),
                state.get("memory_scope", "global"),
            )
        )
        memories = AgentMemory(self.workspace, agent["id"]).recall(
            scope, limit=int(config.get("limit", 5))
        )
        return {str(config.get("output_field", "memory")): memories}

    def _execute_memory_remember(
        self,
        node: dict[str, Any],
        state: dict[str, Any],
        agent: dict[str, Any],
    ) -> dict[str, Any]:
        config = node.get("data", {}).get("config", {})
        scope = str(
            resolve_path(
                state["context"],
                config.get("scope_field", "customer_id"),
                state.get("memory_scope", "global"),
            )
        )
        fields = config.get("fields")
        if fields:
            content = {field: resolve_path(state["context"], field) for field in fields}
        else:
            content = {"input": state["input"], "context": state["context"]}
        memory_id = AgentMemory(self.workspace, agent["id"]).remember(
            scope,
            content,
            kind=str(config.get("kind", "note")),
            run_id=state.get("run_id"),
        )
        return {"memory_id": memory_id, "memory_scope": scope}
