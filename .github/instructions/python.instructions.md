---
applyTo: "**/*.py"
---

# Python Development Instructions

## General

- Use Python 3.13+.
- Follow PEP 8.
- Use type hints for functions, methods, variables where they improve clarity, and public interfaces.
- Prefer explicit, readable code over clever abstractions.
- Do not introduce abstractions without a concrete use case.
- Keep functions and classes focused on one responsibility.
- Avoid premature optimization.
- Do not add unrelated refactoring to a feature task.

## Formatting and linting

Ruff is the source of truth for formatting and linting.

Before completing a task, run:

```bash
make format
make lint
