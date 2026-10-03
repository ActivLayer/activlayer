from activlayer.agent import AgentRepository
from activlayer.graph_runtime import GraphRuntime
from activlayer.knowledge import SharedKnowledge
from activlayer.memory import AgentMemory
from activlayer.spec import RunStatus
from activlayer.workspace import Workspace


def test_orchestrator_routes_to_published_worker(tmp_path):
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example Organization")
    repository = AgentRepository(workspace)
    worker_ids = []
    for name in ("Products", "Services", "Resolution"):
        worker = repository.create(name, agent_type="worker")
        worker["memory"]["enabled"] = True
        repository.save(worker)
        repository.publish(worker["id"])
        worker_ids.append(worker["id"])

    orchestrator = repository.create("Customer Care", agent_type="orchestrator")
    orchestrator["managed_workers"] = worker_ids
    route = repository.get_node(orchestrator, "route")
    route["data"]["config"] = {
        "routes": [{"worker": worker_ids[0], "when_any": ["price", "product"]}],
        "default_worker": worker_ids[2],
    }
    repository.save(orchestrator)
    repository.publish(orchestrator["id"])

    run = GraphRuntime(workspace).start(
        repository.load(orchestrator["id"], published=True),
        {"customer_id": "customer-1", "request": "What is the product price?"},
    )

    assert run.status == RunStatus.SUCCEEDED
    assert run.state["context"]["selected_worker"] == worker_ids[0]
    assert run.state["context"]["delegated_worker"] == worker_ids[0]
    assert AgentMemory(workspace, worker_ids[0]).count() == 1
    assert AgentMemory(workspace, worker_ids[1]).count() == 0


def test_shared_knowledge_is_searchable(tmp_path):
    workspace = Workspace.initialize(tmp_path / ".activlayer", "Example Organization")
    knowledge = SharedKnowledge(workspace)
    knowledge.create_collection("Product Guide")
    knowledge.add("Product Guide", "Savings", "Savings accounts have no monthly fee.")

    results = knowledge.search("monthly savings fee", collections=["product-guide"])

    assert results[0]["title"] == "Savings"
