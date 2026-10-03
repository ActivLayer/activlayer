"""A complete worker with a permission boundary and human approval gate."""

from activlayer import ApprovalPolicy, Runtime, Step, Worker, tool


@tool(description="Draft a customer reply", permission="support.read")
def draft_reply(ticket: str) -> str:
    return f"Thanks for contacting us about: {ticket}. We are looking into it."


@tool(
    description="Publish an approved reply",
    permission="support.write",
    approval=ApprovalPolicy.REQUIRED,
)
def publish_reply(message: str) -> dict[str, str]:
    return {"status": "published", "message": message}


support_worker = Worker(
    name="support-reply",
    description="Draft, review, and publish a customer support reply.",
    steps=(
        Step("draft", draft_reply, lambda state: {"ticket": state["input"]["ticket"]}),
        Step(
            "publish",
            publish_reply,
            lambda state: {"message": state["outputs"]["draft"]},
        ),
    ),
)


if __name__ == "__main__":
    runtime = Runtime("example.db")
    run = runtime.start(
        support_worker,
        {"ticket": "I need to change my delivery address"},
        permissions={"support.read", "support.write"},
    )
    print(f"Run {run.id}: {run.status}")
    run = runtime.approve(run.id, actor="reviewer@example.com", reason="Reply checked")
    print(f"Run {run.id}: {run.status}")
    print(run.state["outputs"]["publish"])
