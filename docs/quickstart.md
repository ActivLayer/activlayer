# Quick start

## Requirements

- Python 3.11 or newer
- Git
- An optional OpenAI-compatible model server for AI nodes

## Install

```bash
git clone https://github.com/ActivLayer/activlayer.git
cd activlayer
git switch community-edition
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Initialize

```bash
activlayer init \
  --organization "Example Organization" \
  --owner owner@example.com
```

## Configure a model

```bash
activlayer llm add local --type ollama --model qwen3:8b
activlayer llm test local
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

