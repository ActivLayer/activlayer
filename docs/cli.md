# CLI guide

The `activlayer` command is the Community Edition control plane. It discovers `.activlayer` in the
current directory or a parent directory. Override discovery with `ACTIVLAYER_HOME` or `--home`.

## Command map

```text
activlayer
├── init                    create a one-organization environment
├── status                  environment dashboard
├── doctor                  configuration and connectivity checks
├── guide                   guided operational workflow
├── serve                   authenticated HTTP API
├── config show|get|set     environment properties
├── user list|add|remove|token
├── llm list|add|use|test|remove
├── connector list|add|test
├── extension list|add|remove
├── chat                    plan and review natural-language design changes
├── knowledge collection-create|collection-list|add|search
├── memory list|search      inspect one worker's isolated memory
├── agent new|list|show|set|workers|validate|import|export|provision|publish|graph
│   └── node list|types|explain|show|add|set|remove|connect|disconnect
└── run start|list|show|resume|approve
```

Every group and command supports `--help`.

`activlayer init` automatically probes the standard loopback endpoints for Ollama, vLLM, and
llama.cpp, plus non-default ports declared by running vLLM and llama.cpp processes. Discovered
servers with at least one model are saved and the first becomes active. Pass `--no-detect-llm` for
isolated or manually configured environments.

## Agent design workflow

Create a definition, browse available node types, add nodes, edit nested configuration, connect the
graph, validate, and publish:

```bash
activlayer agent new "Content Review" --id content-review
activlayer agent node types --category ai
activlayer agent node explain control.approval
activlayer agent node add content-review analyze --type ai.prompt
activlayer agent node set content-review analyze data.config.prompt \
  "Review the submitted content: {content}"
activlayer agent node connect content-review trigger analyze
activlayer agent graph content-review
activlayer agent validate content-review
activlayer agent publish content-review
```

`agent set` changes any non-graph agent property. `agent node set` changes any node property. Dotted
paths create missing intermediate objects. Values are decoded as JSON when valid; use a JSON-quoted
string when a value might otherwise be interpreted as a number, boolean, array, or object.

## Portable definitions

`agent import` installs a JSON file as a draft. `agent provision` combines validation and install,
and `--publish` creates an execution snapshot. `agent export` creates a portable file that can be
opened by another Community environment or Studio.

## Shell completion

```bash
activlayer --install-completion
```

Typer installs completion for the active shell.

## Multi-agent design

Create workers before their orchestrator, publish the workers first, and then publish the
orchestrator:

```bash
activlayer agent new "Product Worker" --id product-worker --type worker
activlayer agent publish product-worker
activlayer agent new "Service Orchestrator" --id service-orchestrator --type orchestrator
activlayer agent workers service-orchestrator product-worker
activlayer agent publish service-orchestrator
```

`agent validate` checks role relationships as well as graph structure. Publication fails when an
orchestrator references a missing, unpublished, or non-worker agent.

Use `activlayer chat "<request>"` to produce a validated design plan. The command displays every
typed operation and asks before changing drafts. `--apply` is intended for automation where the
request and generated plan are already subject to review.
