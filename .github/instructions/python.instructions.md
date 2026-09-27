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
````

Do not suppress a linting rule unless there is a documented reason.

Prefer fixing the underlying problem over adding `# noqa`.

## Type checking

Code should pass the configured type checker.

Do not use `Any` unless there is a clear technical reason.

Avoid unnecessary `cast()` calls.

Do not silence type errors without understanding their cause.

## Async

Backend code uses asynchronous APIs where supported.

Prefer:

* `async def`
* `await`
* `AsyncSession`
* async database drivers
* async HTTP clients

Do not introduce blocking I/O into asynchronous request handlers.

Do not use synchronous database operations from async application code.

## Error handling

Do not catch broad exceptions such as:

```python
except Exception:
```

unless the exception is intentionally handled at an application boundary.

Prefer specific exception types.

Do not hide errors by returning `None` or an empty result when the operation actually failed.

## Logging

Use the application logging system.

Do not use `print()` for application logging.

Never log:

* passwords;
* access tokens;
* refresh tokens;
* API keys;
* secrets;
* session cookies.

## Dependencies

Do not add a dependency when the functionality can reasonably be implemented with the existing stack.

Before adding a dependency:

1. verify that the existing project does not already provide the functionality;
2. consider maintenance and security implications;
3. document why the dependency is required.

## Architecture

Follow the existing project architecture.

Do not move modules or introduce a new architectural pattern unless the task explicitly requires it.

Business logic must not be placed directly in FastAPI routers.

Database access must not be scattered throughout the application.

## Tests

New business logic must have tests.

Bug fixes should include a regression test whenever practical.

Tests must be deterministic.

Do not use real external services in unit tests.

Use factories/fixtures for test data.

## Completion

Before considering a Python task complete:

```bash
make format
make lint
make typecheck
make test
```
