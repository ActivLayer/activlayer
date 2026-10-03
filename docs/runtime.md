# Runtime and reliability

The reference runtime stores runs, approvals, and events in SQLite. A step output and the updated
cursor are committed before the next step starts. A stopped process can re-register the same worker
version and resume the run by identifier.

## Retry behavior

Step failures are retried up to `max_attempts` with a small exponential delay. After the final
attempt, the run becomes `failed` and stores a safe error message. Tool implementations should be
idempotent because a process can fail after an external side effect but before local state commits.

## Status lifecycle

```text
pending → running → waiting_approval → running → succeeded
                └───────────────────────────────→ failed
```

## Event integrity

Each event contains the preceding event's SHA-256 digest. `runtime.store.verify_events(run_id)`
recomputes the chain. This detects editing; it is not a substitute for access controls, backups, or
an external append-only archive.

## Scope of the reference runtime

SQLite is ideal for local development, embedded deployments, and learning. Multi-process leasing,
distributed queues, remote databases, and production scheduling are roadmap items. Extensions can
wrap the public specification while retaining the same worker semantics.

