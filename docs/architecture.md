# Architecture

Community Edition deliberately keeps the execution core small.

```text
Application code
  ├─ Worker definitions
  ├─ Governed tools
  └─ Approval identity/UI
          │
          ▼
ActivLayer Runtime
  ├─ Definition registry
  ├─ Permission enforcement
  ├─ Approval gates
  ├─ Retry and resume loop
  └─ Extension contract
          │
          ▼
Durable Store
  ├─ Runs and state
  ├─ Approval decisions
  └─ Hash-chained events
```

The core does not depend on an LLM SDK. Model calls are tools like any other capability, so teams can
choose a hosted model, a local model, a deterministic service, or no model at all. This keeps
governance and durability independent from inference vendors.

