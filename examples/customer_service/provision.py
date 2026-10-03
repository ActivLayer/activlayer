"""Provision a local customer-service organization with one orchestrator and three workers."""

from __future__ import annotations

import argparse
from pathlib import Path

from activlayer.agent import AgentRepository
from activlayer.knowledge import SharedKnowledge
from activlayer.memory import AgentMemory
from activlayer.workspace import Workspace

WORKERS = {
    "product-advisor": {
        "name": "Product and Pricing Advisor",
        "description": "Answers questions about products, eligibility, features, and pricing.",
        "collections": ["bank-products", "bank-pricing"],
        "prompt": (
            "Answer the customer request using only the supplied knowledge. State when the "
            "knowledge does not contain an answer. Do not invent fees, rates, or eligibility."
        ),
    },
    "service-guide": {
        "name": "Service and Procedure Guide",
        "description": "Guides customers through account, card, and digital service procedures.",
        "collections": ["bank-services", "bank-procedures"],
        "prompt": (
            "Give safe step-by-step service guidance from the supplied knowledge. Never request "
            "a password, PIN, one-time code, or full card number."
        ),
    },
    "request-resolution": {
        "name": "Request Resolution Worker",
        "description": "Handles complaints, disputes, request status, and escalation guidance.",
        "collections": ["bank-procedures", "bank-services"],
        "prompt": (
            "Classify the request, explain the approved next step from the supplied knowledge, "
            "and clearly identify any required human escalation."
        ),
    },
}

KNOWLEDGE = {
    "bank-products": (
        "Bank Products",
        "Retail product facts",
        "Everyday Account",
        "An everyday transaction account supports transfers, bill payment, and a debit card. "
        "Opening requires identity and address verification. Product availability is subject to "
        "local eligibility checks.",
    ),
    "bank-services": (
        "Bank Services",
        "Customer service capabilities",
        "Digital and card services",
        "Customers can request card controls, statement access, beneficiary management, and "
        "profile updates. Sensitive changes require strong authentication and may require review.",
    ),
    "bank-pricing": (
        "Bank Pricing",
        "Illustrative fee schedule",
        "Standard pricing",
        "The everyday account has a monthly service fee of 5 units. Domestic digital transfers "
        "cost 1 unit. Fees are illustrative and must be confirmed against the current schedule.",
    ),
    "bank-procedures": (
        "Bank Procedures",
        "Approved operating procedures",
        "Customer request handling",
        "For a lost card, place a card block immediately and arrange replacement after identity "
        "verification. For a disputed transaction, record the date, amount, and merchant, then "
        "open a human-reviewed dispute. Never ask for a PIN, password, or one-time code.",
    ),
}


def worker_graph(prompt: str, collections: list[str]) -> dict:
    return {
        "nodes": [
            {
                "id": "request",
                "type": "trigger.api",
                "data": {"label": "Customer request", "config": {}},
            },
            {
                "id": "knowledge",
                "type": "knowledge.search",
                "data": {
                    "label": "Retrieve approved knowledge",
                    "config": {
                        "query": "{request}",
                        "collections": collections,
                        "top_k": 4,
                    },
                },
            },
            {
                "id": "answer",
                "type": "ai.prompt",
                "data": {
                    "label": "Prepare response",
                    "config": {"prompt": prompt, "temperature": 0, "max_tokens": 500},
                },
            },
            {
                "id": "result",
                "type": "output.result",
                "data": {
                    "label": "Customer response",
                    "config": {"expose": ["text", "model"]},
                },
            },
        ],
        "edges": [
            {"id": "request-knowledge", "source": "request", "target": "knowledge"},
            {"id": "knowledge-answer", "source": "knowledge", "target": "answer"},
            {"id": "answer-result", "source": "answer", "target": "result"},
        ],
    }


def provision(home: Path, *, base_url: str, model: str) -> Workspace:
    workspace = Workspace.initialize(home, "Community Banking Services")
    config = workspace.config
    config["providers"]["local"] = {
        "type": "ollama",
        "base_url": base_url.rstrip("/"),
        "model": model,
        "api_key_env": None,
        "timeout_seconds": 120,
    }
    config["active_provider"] = "local"
    workspace.save_config(config)

    knowledge = SharedKnowledge(workspace)
    for collection_id, (name, description, title, content) in KNOWLEDGE.items():
        knowledge.create_collection(name, description)
        knowledge.add(collection_id, title, content, metadata={"demo": True})

    repository = AgentRepository(workspace)
    for worker_id, definition in WORKERS.items():
        worker = repository.create(
            definition["name"],
            agent_id=worker_id,
            description=definition["description"],
            agent_type="worker",
        )
        worker["domain"] = "bank-customer-service"
        worker["memory"] = {
            "enabled": True,
            "auto_recall": True,
            "auto_remember": True,
            "scope_field": "customer_id",
            "recall_limit": 5,
        }
        worker["knowledge"] = {"collections": definition["collections"], "top_k": 4}
        worker["system_prompt"] = (
            "You are a careful customer-service worker. Use approved knowledge, protect sensitive "
            "data, distinguish facts from uncertainty, and return a concise answer."
        )
        worker["graph"] = worker_graph(definition["prompt"], definition["collections"])
        repository.save(worker)
        repository.publish(worker_id)
        AgentMemory(workspace, worker_id)

    orchestrator = repository.create(
        "Customer Service Orchestrator",
        agent_id="customer-service-orchestrator",
        description="Routes customer requests to one specialized managed worker.",
        agent_type="orchestrator",
    )
    orchestrator["domain"] = "bank-customer-service"
    orchestrator["managed_workers"] = list(WORKERS)
    route = repository.get_node(orchestrator, "route")
    route["data"]["config"] = {
        "routes": [
            {
                "worker": "product-advisor",
                "when_any": ["product", "account", "price", "pricing", "fee", "rate"],
            },
            {
                "worker": "service-guide",
                "when_any": ["card", "login", "statement", "transfer", "beneficiary"],
            },
            {
                "worker": "request-resolution",
                "when_any": ["complaint", "dispute", "problem", "status", "escalate"],
            },
        ],
        "default_worker": "request-resolution",
        "use_llm": False,
    }
    repository.save(orchestrator)
    repository.publish(orchestrator["id"])
    return workspace


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--home", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434/v1")
    parser.add_argument("--model", default="dima-language:latest")
    arguments = parser.parse_args()
    workspace = provision(arguments.home, base_url=arguments.base_url, model=arguments.model)
    print(workspace.root)


if __name__ == "__main__":
    main()
