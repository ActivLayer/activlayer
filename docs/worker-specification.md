# Agent Worker specification

The Python types in `activlayer.spec` are the executable reference for specification version 0.1.

## Worker fields

| Field | Required | Meaning |
|---|---:|---|
| `name` | yes | Stable worker identifier |
| `version` | yes | Definition version; defaults to `1` |
| `description` | no | Human-readable purpose |
| `steps` | yes | Ordered, non-empty collection of uniquely named steps |
| `labels` | no | Deployment-independent metadata |

## Step fields

| Field | Required | Meaning |
|---|---:|---|
| `name` | yes | Unique identifier within the worker |
| `tool` | yes | Governed callable to invoke |
| `arguments` | yes | Function deriving keyword arguments from run state |
| `save_as` | no | Output key; defaults to the step name |
| `max_attempts` | no | Bounded attempts; defaults to `3` |

## Tool fields

| Field | Required | Meaning |
|---|---:|---|
| `name` | yes | Non-empty identifier without whitespace |
| `function` | yes | Python callable |
| `description` | no | Human-readable capability description |
| `permission` | no | Permission required at invocation time |
| `approval` | no | `never` or `required` |

Worker definitions should be serializable at their boundary, while tool implementations and argument
factories remain normal application code. Inputs and outputs stored by the reference runtime must be
JSON-compatible.

