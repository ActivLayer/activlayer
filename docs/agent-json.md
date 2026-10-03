# Agent JSON reference

Agent JSON is the portable contract shared with ActivLayer Studio. Community Edition stores drafts
and published snapshots as readable JSON files.

## Top-level properties

| Property | Required | Meaning |
|---|---:|---|
| `schema_version` | recommended | Agent document schema version |
| `id` | yes | Stable environment-unique identifier |
| `name` | yes | Human-readable name |
| `description` | no | Purpose and boundary |
| `agent_type` | yes | `worker` or `orchestrator` |
| `managed_workers` | orchestrator | Allowlisted worker IDs |
| `memory` | no | Worker recall and write-back settings |
| `knowledge` | no | Shared collection IDs and retrieval limit |
| `domain` | no | Industry-neutral classification |
| `version` | no | Published definition version |
| `status` | no | `draft` or `published` |
| `trigger` | no | Trigger metadata |
| `system_prompt` | no | Default instruction for AI nodes |
| `policy` | no | Definition-level policy metadata |
| `graph` | yes | `nodes` and directed `edges` |

## Node shape

```json
{
  "id": "analyze",
  "type": "ai.prompt",
  "data": {
    "label": "Analyze",
    "subtitle": "Structured review",
    "disabled": false,
    "config": {
      "prompt": "Analyze {request}",
      "when": "priority == high",
      "permission": "requests.read",
      "approval_required": false,
      "max_attempts": 3
    }
  }
}
```

All node types can use `when`, `permission`, `approval_required`, and `max_attempts`. The runtime
evaluates conditions without executing arbitrary Python code.

## Graph validation

Validation requires unique node and edge identifiers, valid edge endpoints, at least one trigger and
output, and an acyclic graph. Execution follows deterministic topological order.

Browse executable nodes with `activlayer agent node types` and inspect configuration examples with
`activlayer agent node explain <type>`.
