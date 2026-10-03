# Quick start

## Requirements

- Python 3.11 or newer
- `curl` for the one-command installer
- An optional OpenAI-compatible model server for AI nodes

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/ActivLayer/activlayer/community-edition/install.sh | sh
activlayer --version
```

The installer uses an isolated environment and makes `activlayer` available from any directory. If
it adds `~/.local/bin` to your shell profile, open a new terminal once after installation.

## Initialize

```bash
activlayer init \
  --organization "Example Organization" \
  --owner owner@example.com
```

Initialization automatically discovers Ollama, vLLM, and llama.cpp on their standard local ports
and on non-default ports declared by running vLLM or llama.cpp processes. It configures every
provider that reports a model and selects the first one. If none is running, continue with manual
configuration below. Use `--no-detect-llm` to skip discovery.

## Configure a model

```bash
activlayer llm add local --type ollama --model qwen3:8b
activlayer llm list
activlayer llm test
```

AI nodes require a model provider. Trigger, rule, approval, HTTP, decision, and output nodes run
without one.

## Provision and run

```bash
activlayer agent provision examples/request_review.json --publish
activlayer agent graph request-review --published

activlayer run start request-review \
  --input '{"request":"Review the weekly report"}' \
  --permission requests.approve \
  --actor owner@example.com
```

The run processes the trigger and AI node, then pauses durably at the approval node.

```bash
activlayer run list
activlayer run show <run-id> --events
activlayer run approve <run-id> --actor owner@example.com --reason "Checked"
```

Continue with the [CLI guide](cli.md) and [Agent JSON reference](agent-json.md).
