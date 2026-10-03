<div align="center">
  <a href="https://www.activlayer.com/">
    <img src="docs/assets/readme-hero.svg" alt="ActivLayer — governed AI workers" width="100%" />
  </a>
</div>

<div align="center">

[![Community Edition](https://img.shields.io/badge/edition-community-8B5CF6?style=flat-square)](COMMUNITY.md)
[![Python](https://img.shields.io/badge/python-3.11%2B-3776AB?style=flat-square&logo=python&logoColor=white)](pyproject.toml)
[![License](https://img.shields.io/badge/license-Apache--2.0-22C55E?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-pytest-0A9EDC?style=flat-square&logo=pytest&logoColor=white)](tests)

**The open framework for building and operating governed AI workers.**

[Website](https://www.activlayer.com/) · [Documentation](https://www.activlayer.com/documentation/) · [Articles](https://www.activlayer.com/articles/) · [Examples](examples) · [Community](COMMUNITY.md)

</div>

---

ActivLayer turns agents into dependable workers that can execute real business processes. Define a
worker in code, give it tools with explicit permissions, place human approval gates around sensitive
actions, and retain a durable, verifiable record of every run.

The Community Edition is self-hosted, model-agnostic, and industry-neutral. It has no mandatory
cloud account, telemetry, or artificial limits on workers and runs.

## Why ActivLayer?

Most agent frameworks help a model call a function. ActivLayer focuses on what comes next: operating
that behavior safely and predictably inside a real organization.

| Build | Govern | Operate | Extend |
|---|---|---|---|
| Code-first workers and tools | Explicit permissions | Durable run state | Model-agnostic by design |
| Versioned worker definitions | Human approval gates | Retries and resumability | Plain Python tools |
| Typed public specification | Auditable actions | Local, self-hosted storage | Reusable extensions |

## An Agent Worker in 60 seconds

```python
from activlayer import ApprovalPolicy, Runtime, Step, Worker, tool

@tool(permission="support.read")
def draft_reply(ticket: str) -> str:
    return f"Thanks for contacting us about: {ticket}"

@tool(permission="support.write", approval=ApprovalPolicy.REQUIRED)
def publish_reply(message: str) -> dict:
    return {"status": "published", "message": message}

worker = Worker(
    name="support-reply",
    steps=(
        Step("draft", draft_reply,
             lambda state: {"ticket": state["input"]["ticket"]}),
        Step("publish", publish_reply,
             lambda state: {"message": state["outputs"]["draft"]}),
    ),
)

runtime = Runtime("activlayer.db")
run = runtime.start(
    worker,
    {"ticket": "I need to change my delivery address"},
    permissions={"support.read", "support.write"},
)

# The run is durable and paused before the write action.
assert run.status == "waiting_approval"

run = runtime.approve(run.id, actor="reviewer@example.com", reason="Reply checked")
assert run.status == "succeeded"
```

Tools are ordinary Python functions. Governance is part of their definition rather than an
afterthought. When execution stops for approval—or because a process restarts—the run remains in
SQLite and can continue from the exact durable step.

## Quick start

```bash
git clone https://github.com/activlayer/activlayer.git
cd activlayer
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
python examples/approval_worker.py
```

Python 3.11 or newer is required. The core has no runtime dependencies outside the standard
library.

## How it works

```text
Input
  │
  ▼
Agent Worker ──► durable step ──► permission check ──► approval gate
  ▲                                                        │
  │                                                        ▼
  └──────── durable state ◄── tool result ◄── governed tool call

Every transition ──► hash-chained event log
```

An **Agent Worker** is a long-running, governed software worker that uses AI models and tools to
execute business tasks reliably within explicit permissions, approval policies, and operational
controls. ActivLayer does not prescribe which model, prompt framework, or infrastructure you use.

## Community Edition

The open-source edition includes:

- A code-first Python SDK and public Agent Worker specification
- A durable, self-hosted runtime backed by SQLite
- Governed tools, permissions, and human approval checkpoints
- Retry handling, resumable runs, and hash-chained execution events
- An extension contract for reusable workers and tools
- Runnable examples, tests, documentation, and GitHub community support

See [Community Edition](COMMUNITY.md) for the product boundary and design commitments.

## Documentation

| Guide | What you will learn |
|---|---|
| [Quick start](docs/quickstart.md) | Install the SDK and run your first worker |
| [Core concepts](docs/concepts.md) | Workers, steps, tools, runs, permissions, and approvals |
| [Worker specification](docs/worker-specification.md) | The stable public contract and validation rules |
| [Permissions and approvals](docs/governance.md) | Put enforceable controls around tool use |
| [Runtime and reliability](docs/runtime.md) | Persistence, retries, resumability, and event integrity |
| [Extensions](docs/extensions.md) | Package and share reusable capabilities |
| [Architecture](docs/architecture.md) | Understand the Community runtime components |
| [Roadmap](ROADMAP.md) | See what is planned and help shape priorities |

For broader product and implementation guidance, visit the
[ActivLayer documentation](https://www.activlayer.com/documentation/).

## Learn from the field

The [ActivLayer articles](https://www.activlayer.com/articles/) explore the operating patterns behind
governed AI work:

- [Defining human checkpoints](https://www.activlayer.com/documentation/define-a-checkpoint/) — pause
  a workflow for review under policy.
- [Maker-checker for machines](https://www.activlayer.com/articles/maker-checker-for-machines/) —
  apply separation of duties to AI-assisted operations.
- [Browse all articles](https://www.activlayer.com/articles/) — practical writing on agent
  operations, control, and reliability.

## Project status

Community Edition is an early release. Its public interfaces will evolve as the community tests them
against real workloads. Pin versions, review the [changelog](CHANGELOG.md), and open a discussion
before depending on an undocumented behavior.

## Contributing

We welcome bug reports, documentation improvements, examples, integrations, and focused proposals.
Start with [CONTRIBUTING.md](CONTRIBUTING.md), read our [Code of Conduct](CODE_OF_CONDUCT.md), and use
GitHub Discussions for design questions.

## Security

Please do not report security vulnerabilities through a public issue. Follow the private process in
[SECURITY.md](SECURITY.md).

## Community and contact

- Ask usage questions in [GitHub Discussions](https://github.com/activlayer/activlayer/discussions)
- Report reproducible defects in [GitHub Issues](https://github.com/activlayer/activlayer/issues)
- For product or partnership inquiries, email [hello@activlayer.com](mailto:hello@activlayer.com)

## License

ActivLayer Community Edition is licensed under the [Apache License 2.0](LICENSE).

