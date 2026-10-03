# Quick start

## Requirements

- Python 3.11 or newer
- Git

## Install from source

```bash
git clone https://github.com/activlayer/activlayer.git
cd activlayer
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

On Windows PowerShell, activate the environment with `.venv\Scripts\Activate.ps1`.

## Run the example

```bash
python examples/approval_worker.py
```

The example creates a local `example.db`, executes its first step, pauses before a protected write,
records a human approval, and completes. Delete the database whenever you want a fresh local run.

## Run the tests

```bash
pytest
```

Continue with [Core concepts](concepts.md) or open
[`examples/approval_worker.py`](../examples/approval_worker.py) to modify the worker.

