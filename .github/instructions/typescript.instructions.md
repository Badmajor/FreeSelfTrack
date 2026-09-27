
---
applyTo: "**/*.{ts,tsx}"
---

# TypeScript Development Instructions

## General

- Use TypeScript in strict mode.
- Prefer explicit types at public boundaries.
- Avoid `any`.
- Do not use `@ts-ignore` unless absolutely necessary and documented.
- Prefer `unknown` over `any` when the type is genuinely unknown.
- Keep components and modules focused.
- Avoid unnecessary abstractions.

## React

Use functional components.

Prefer composition over inheritance.

Components should not contain large amounts of business logic.

Move reusable business logic into hooks or dedicated modules when appropriate.

Do not duplicate business rules between components.

## Server state

Server state must have a clear owner.

Prefer the configured data-fetching/query library rather than manually duplicating server state in local component state.

Do not maintain a second copy of API data unless there is a specific reason.

## API

The backend API is the source of truth.

Do not invent API response structures on the frontend.

Do not hardcode backend-generated identifiers.

Prefer generated API types when the project provides them.

When the API contract changes, update the generated client/types instead of manually editing generated files.

## Forms

Validate user input on the frontend for good UX.

Do not rely on frontend validation for security.

The backend remains responsible for authoritative validation.

## State

Use local component state for local UI state.

Use the project's configured state/query solution for shared or server state.

Avoid introducing a global state store for a problem that can be solved locally.

## Kanban

Kanban columns are derived from project statuses returned by the backend.

Never hardcode:

- status IDs;
- status names;
- number of columns;
- workflow transitions.

The backend is the source of truth for project workflow.

Column presentation settings such as width may be stored as user preferences.

## UI

Reusable UI components should be placed in the project's shared component structure.

Do not duplicate identical UI logic across pages.

Handle:

- loading states;
- empty states;
- errors;
- disabled states.

## Accessibility

Interactive elements must be keyboard accessible.

Use semantic HTML where appropriate.

Buttons should be buttons.

Links should be links.

Forms must have accessible labels.

## Styling

Follow the project's existing styling approach.

Do not introduce a second styling framework without explicit approval.

Avoid hardcoded values when an existing design token or theme value exists.

## Tests

Add tests for meaningful component behavior.

Do not write tests that only verify implementation details.

Prefer testing observable user behavior.

## Completion

Before completing a frontend task:

```bash
make lint
make typecheck
make test
make build
```
