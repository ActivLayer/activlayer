"""Built-in node catalog used by the CLI, validator, and documentation."""

from __future__ import annotations

from typing import Any

NODE_CATALOG: dict[str, dict[str, Any]] = {
    "trigger.manual": {
        "category": "trigger",
        "description": "Start from the CLI or HTTP API and expose the submitted input.",
        "config": {},
    },
    "trigger.api": {
        "category": "trigger",
        "description": "Declare an API-triggered worker entry point.",
        "config": {"permission": "optional permission required to start"},
    },
    "trigger.schedule": {
        "category": "trigger",
        "description": "Declare schedule metadata for an external scheduler.",
        "config": {"cron": "0 * * * *"},
    },
    "ai.prompt": {
        "category": "ai",
        "description": "Call the active OpenAI-compatible model with a prompt and run context.",
        "config": {
            "prompt": "Instruction with {field} templates",
            "provider": "optional provider name",
            "temperature": 0,
            "max_tokens": 1000,
        },
    },
    "ai.extract": {
        "category": "ai",
        "description": "Ask the model to extract configured fields into JSON.",
        "config": {"fields": ["field_name"], "prompt": "optional extraction instruction"},
    },
    "ai.judge": {
        "category": "ai",
        "description": "Ask the model for a structured judgment.",
        "config": {"prompt": "Judgment criteria", "temperature": 0},
    },
    "rule.completeness": {
        "category": "rule",
        "description": "Require a set of dotted input or context fields.",
        "config": {"required": ["field"], "on_fail": "review"},
    },
    "rule.limit": {
        "category": "rule",
        "description": "Compare a numeric field with a maximum.",
        "config": {"field": "amount", "max": 1000, "op": "<=", "on_breach": "review"},
    },
    "rule.membership": {
        "category": "rule",
        "description": "Require a field value to belong to an allowed set.",
        "config": {"field": "status", "allowed": ["active"], "on_fail": "review"},
    },
    "rule.compute": {
        "category": "rule",
        "description": "Compute a field from a safe two-operand arithmetic formula.",
        "config": {"target": "total", "formula": "subtotal + tax", "round": 2},
    },
    "rule.condition": {
        "category": "rule",
        "description": "Evaluate a safe condition without executing Python code.",
        "config": {"condition": "score >= 0.8", "on_fail": "review"},
    },
    "control.approval": {
        "category": "control",
        "description": "Pause durably until a user records approval.",
        "config": {"approval_reason": "Human review required"},
    },
    "orchestrator.route": {
        "category": "orchestration",
        "description": (
            "Select one managed worker using deterministic routes or an optional model."
        ),
        "config": {
            "routes": [{"worker": "worker-id", "when_any": ["keyword"]}],
            "default_worker": "worker-id",
            "use_llm": False,
        },
    },
    "orchestrator.delegate": {
        "category": "orchestration",
        "description": "Run the selected managed worker as a durable child run.",
        "config": {"worker_from": "selected_worker"},
    },
    "knowledge.search": {
        "category": "knowledge",
        "description": "Search the organization's shared knowledge collections.",
        "config": {"query": "{request}", "collections": [], "top_k": 5},
    },
    "memory.recall": {
        "category": "memory",
        "description": "Recall records from this worker's isolated memory database.",
        "config": {"scope_field": "customer_id", "limit": 5},
    },
    "memory.remember": {
        "category": "memory",
        "description": "Write selected context fields to this worker's isolated memory database.",
        "config": {"scope_field": "customer_id", "fields": [], "kind": "note"},
    },
    "tool.http": {
        "category": "tool",
        "description": "Call a configured HTTP connector under permission and approval controls.",
        "config": {
            "connector": "connector-name",
            "endpoint": "/path",
            "method": "POST",
            "permission": "system.write",
            "approval_required": False,
        },
    },
    "decision.route": {
        "category": "decision",
        "description": "Choose pass or review from the accumulated rule flags.",
        "config": {"pass_label": "approve", "review_label": "review"},
    },
    "route.assign": {
        "category": "route",
        "description": "Attach assignment metadata to the run.",
        "config": {"role": "Reviewer", "reason": "Routed by policy", "four_eyes": False},
    },
    "output.result": {
        "category": "output",
        "description": "Compose the final run result or expose selected fields.",
        "config": {"expose": ["optional.field"]},
    },
}


def node_help(node_type: str) -> dict[str, Any] | None:
    direct = NODE_CATALOG.get(node_type)
    if direct:
        return direct
    if node_type.startswith("integration."):
        return {
            "category": "integration",
            "description": "Studio integration executed as a governed HTTP connector call.",
            "config": NODE_CATALOG["tool.http"]["config"],
        }
    if node_type.startswith("ai."):
        return NODE_CATALOG["ai.prompt"]
    return None
