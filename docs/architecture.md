# Architecture

```text
                    ┌────────────────────────────┐
                    │ one organization / 3 users │
                    └──────────────┬─────────────┘
                                   │ token
              ┌────────────────────┴────────────────────┐
              ▼                                         ▼
       Rich CLI control plane                  FastAPI runtime API
              │                                         │
              ├── environment/users                     ├── start/resume
              ├── LLMs/connectors                       ├── approve
              └── agent graph editor                     └── inspect/events
              │                                         │
              └────────────────────┬────────────────────┘
                                   ▼
                         Studio-compatible JSON
                          drafts / published
                                   │
                                   ▼
                            Graph Runtime
              ┌────────────────────┼────────────────────┐
              ▼                    ▼                    ▼
       governance checks       node executors      durable cursor
       permission/approval     AI/rule/HTTP/...    retries/trace
              └────────────────────┼────────────────────┘
                                   ▼
                         SQLite + event chain
```

## Filesystem

```text
.activlayer/
├── config.json
├── users.json              private, mode 600
├── secrets.json            private, mode 600
├── state.db
├── agents/
│   ├── drafts/
│   └── published/
└── logs/
```

The model layer is deliberately outside the runtime core. AI nodes use an OpenAI-compatible client;
all other node families remain deterministic or invoke explicit connectors.

