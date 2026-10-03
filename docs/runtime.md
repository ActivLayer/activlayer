# Runtime and reliability

The graph runtime validates a definition, computes deterministic topological order, stores a complete
run record, and advances one node at a time. It commits output and the cursor before moving forward.

## Durable state

SQLite stores run identity, definition version, exact definition snapshot, input, accumulated
context, node outputs, attempts, trace, permissions, status, and cursor. Re-registering code is not
required to resume a graph run because the definition is stored with it.

## Status lifecycle

```text
pending → running → waiting_approval → running → succeeded
                └───────────────────────────────→ failed
```

## Retry behavior

Node failures retry with a bounded exponential delay up to `max_attempts`. After the final attempt,
the run becomes `failed`. HTTP tools should use application-level idempotency keys because any local
runtime can stop after an external side effect but before recording its result.

## Fail-closed execution

Missing permissions stop execution. Unknown node types and uninstalled functions fail rather than
being silently skipped. Conditions use a limited expression language and never evaluate Python.

## Event integrity

Every run event includes the preceding event's SHA-256 digest. `verify_events(run_id)` recomputes the
chain. This detects editing but does not replace access controls, backups, or an external append-only
archive.

## Current execution boundary

Community Edition 0.2 is a single-host, single-process reference runtime. Distributed leasing,
parallel branches, external queues, cancellation, schedules, and pluggable database stores remain on
the roadmap.

