# Orchestration, memory, knowledge, and design chat

## Agent types

An agent definition declares `agent_type` as either `worker` or `orchestrator`.

- A worker executes domain work and cannot manage other agents.
- An orchestrator declares `managed_workers` and can route to and delegate one child run to those
  workers. The runtime rejects self-management, missing workers, nested orchestrators, unpublished
  workers, and delegation outside the allowlist.

The built-in `orchestrator.route` node supports deterministic keyword routes and optional model
routing. Model output must name exactly one managed worker. `orchestrator.delegate` starts a durable
child run with the parent's input, permissions, and actor identity.

## Worker memory

When `memory.enabled` is true, the worker receives its own database at
`memory/<worker-id>.db`. Entries are partitioned again by a configurable scope such as
`customer_id`. Automatic recall and write-back can be disabled independently. Explicit
`memory.recall` and `memory.remember` nodes are also available.

Do not store passwords, PINs, one-time codes, full payment-card data, or unneeded personal data in
memory. Retention and deletion policy remain the self-hosting organization's responsibility.

## Shared knowledge

The organization knowledge database stores named collections and documents. Workers select their
approved collections through `knowledge.collections` or a `knowledge.search` node. Search is local
and deterministic. Community Edition currently uses lexical relevance scoring and does not require
an embedding service.

## Safe design chat

The design assistant supplies the model only with agent summaries, the built-in node catalog, and a
strict operation schema. Model output is data, never executable code. The allowlist contains:

- `create_agent`, `set_agent`, and `set_managed_workers`
- `add_node`, `set_node`, and `remove_node`
- `connect` and `disconnect`

Publishing, agent deletion, secret access, connector execution, shell commands, and arbitrary file
writes are not operations. Protected identity, graph-root, status, and version properties cannot be
set. Plans are limited to 50 operations and are validated as a complete staged organization before
writing. The CLI shows the plan and requires confirmation unless `--apply` is explicitly supplied.
Existing drafts are copied to a timestamped backup directory before atomic replacement.

The assistant changes drafts only. Use `activlayer agent validate` and `activlayer agent publish`
for the explicit release step.
