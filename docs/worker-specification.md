# Agent Worker specification

Specification version 1.0 is represented by Studio-compatible JSON and validated by
`activlayer.agent`.

An agent requires `id`, `name`, and a `graph` containing non-empty `nodes` and an `edges` array.
Every node requires a unique `id` and dotted `type`. Every edge source and target must refer to a
node. The graph must be acyclic and include at least one `trigger.*` and `output.*` node.

The runtime executes nodes in deterministic topological order. Each node may declare:

| Configuration | Meaning |
|---|---|
| `when` | Safe expression that controls whether the node runs |
| `permission` | Required permission string |
| `approval_required` | Pause before the node until approved |
| `approval_reason` | Explanation shown to the reviewer |
| `max_attempts` | Bounded execution attempts; default `3` |
| `provider` | LLM provider override for AI nodes |

Agent inputs and node outputs must be JSON-compatible. Extensions may register handlers for custom
node types while preserving the same persistence and governance lifecycle.

See [Agent JSON reference](agent-json.md) for the complete shape.

