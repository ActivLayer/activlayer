# Changelog

All notable changes to ActivLayer Community Edition are documented here.

## 0.3.2 — 2026-10-03

- Automatic discovery and configuration of local Ollama, vLLM, and llama.cpp providers during
  environment initialization, including declared non-default vLLM and llama.cpp ports
- Clear provider-discovery results and next steps in the initialization screen
- Redesigned installer with visible stages, version and path details, a success panel, and optional
  verbose package logs through `ACTIVLAYER_VERBOSE=1`

## 0.3.1 — 2026-10-03

- One-command, no-root installer for Linux and macOS
- Isolated installation with a globally available `activlayer` command
- Idempotent installation command that also upgrades an existing installation

## 0.3.0 — 2026-10-03

- Explicit `worker` and `orchestrator` agent types with managed-worker allowlists
- Deterministic or model-assisted routing and durable child-run delegation
- Separate SQLite memory database for every worker
- Shared organization knowledge collections and local retrieval
- Safe natural-language design chat with typed operations, staged validation, confirmation, and
  draft backups
- CLI commands for roles, relationships, knowledge, memory, and design chat
- Runnable customer-service organization with one orchestrator and three specialized workers

## 0.2.0 — 2026-10-03

- Single-organization environment with an enforced three-user ceiling
- Rich CLI for configuration, users, providers, connectors, agents, nodes, and runs
- Studio-compatible Agent Worker JSON import, export, editing, validation, and publication
- Operational graph runtime with durable definition snapshots and node cursors
- OpenAI-compatible inference for Ollama, vLLM, llama.cpp, and custom endpoints
- Permission enforcement, approval checkpoints, retries, conditional nodes, and event chains
- Authenticated FastAPI service with per-user access-token rotation
- Built-in node catalog, example Agent Worker, Docker image, and Compose definition
- Expanded end-to-end test coverage

## 0.1.0 — 2026-10-03

- Initial public Agent Worker specification
- Code-first tools, steps, and workers
- SQLite-backed durable execution
- Permission enforcement and human approval gates
- Bounded retries and resumable runs
- Hash-chained execution event history
- Extension contract, example, tests, and documentation
