# Core concepts

## Environment

An environment belongs to one organization. It holds up to three users, model and connector
configuration, private secrets, agent definitions, and runtime state.

## Agent Worker

An Agent Worker is a versioned JSON definition containing metadata, policy, and a directed acyclic
graph. Drafts are editable. Published definitions are execution snapshots.

## Node

A node is one durable operation. Its dotted type selects an executor, such as `ai.prompt`,
`rule.completeness`, `control.approval`, `tool.http`, or `output.result`. Configuration lives under
`data.config`, matching Studio output.

## Run

A run is one durable execution of a published definition. It retains the exact definition, input,
context, outputs, attempts, trace, permissions, actor, and node cursor.

## Permission

A permission is an application-defined string attached to a node, such as `records.read` or
`records.write`. The runtime checks the run's granted permissions immediately before execution.

## Approval

An approval is a human decision attached to a run and node. An explicit `control.approval` node—or
any node with `approval_required`—pauses before executing. The actor and reason enter the event log.

## Provider and connector

A provider is an OpenAI-compatible model endpoint. A connector is a governed HTTP endpoint used by
tools and integration nodes. Keys are referenced by environment variable or stored in the private
local secret file.

## Event

Every run transition appends an event containing the preceding event's hash. Recomputing the chain
detects later alteration.

