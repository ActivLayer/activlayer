# Extensions

Extensions add custom node types or named functions while retaining Community Edition persistence,
permissions, approvals, retries, and events.

```python
from activlayer import GraphRuntime


def execute_lookup(node, state):
    key = node["data"]["config"]["key"]
    return {"value": state["context"].get(key)}


def install(runtime: GraphRuntime) -> None:
    runtime.register_handler("example.lookup", execute_lookup)
```

Place the module in the environment's Python path, then enable it explicitly:

```bash
activlayer extension add my_package.activlayer_extension
activlayer extension list
```

A module can export `install(runtime)` or an `extension` object with `name`, `version`, and
`install(runtime)`. Function-call nodes resolve handlers registered as `function:<name>`.

Extensions execute inside the server process and have the same authority as the host application.
Install only reviewed code, declare required permissions, avoid hidden network activity, and never
collect telemetry without explicit operator consent.

