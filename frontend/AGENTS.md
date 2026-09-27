# Frontend instructions

## Stack

- TypeScript
- React
- Vite
- TanStack Query
- React Router

## Rules

- Strict TypeScript.
- Do not use `any` unless explicitly justified.
- API types should be generated from OpenAPI where possible.
- Server state belongs to TanStack Query.
- Do not duplicate server state in local stores.
- Components should remain focused.
- Business logic should not be duplicated between pages.

## Kanban

Kanban state must be derived from project statuses.

Do not hardcode:

- column names;
- status IDs;
- number of columns.

The backend is the source of truth for project workflow.
