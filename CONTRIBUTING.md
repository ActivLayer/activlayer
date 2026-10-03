# Contributing

Thank you for helping make governed AI workers accessible to everyone.

## Before you start

- Search existing issues and discussions.
- Use a discussion for design proposals and an issue for reproducible defects.
- Keep pull requests focused. Large changes should have an agreed design first.
- Never include production data, personal information, secrets, customer material, or generated
  artifacts in a contribution.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
ruff check .
```

Add tests for behavioral changes and update the relevant documentation. Public API changes should
also update the worker specification and changelog.

## Pull requests

A maintainer will review correctness, compatibility, security implications, tests, and clarity.
By submitting a contribution, you agree that it is licensed under the project's Apache License 2.0.

