
These instructions apply to all files under `frontend/`.

The repository root `AGENTS.md` applies in addition to these instructions.

---

# Frontend stack

- TypeScript
- React
- Vite
- React Router
- TanStack Query
- ESLint

Use the existing project configuration and conventions.

---

# TypeScript

Use strict TypeScript.

Avoid `any`.

Prefer:

- explicit domain types;
- discriminated unions where appropriate;
- type-safe API clients;
- narrow types;
- reusable interfaces/types for shared concepts.

Do not silence type errors with unnecessary casts.

Avoid:

```ts
as any
````

unless there is a documented and unavoidable reason.

---

# Backend API is the source of truth

The frontend must treat the backend API as authoritative for:

* domain data;
* permissions;
* workflow;
* task status;
* project configuration;
* validation.

Do not duplicate backend business rules unnecessarily.

Frontend validation exists primarily for user experience.

The backend must still validate all important rules.

---

# API client

Keep API communication centralized and consistent.

Do not scatter raw HTTP requests throughout unrelated components.

Use the project's configured API client and generated types when available.

When the API contract changes:

1. update the backend contract;
2. regenerate API types/client if applicable;
3. update frontend consumers;
4. update relevant tests.

Do not manually create frontend types that contradict the backend API.

---

# State management

Separate server state from local UI state.

Use TanStack Query for server state where appropriate.

Local component state should be used for:

* temporary UI state;
* form state;
* visual preferences;
* interaction state.

Do not duplicate large amounts of server state in global frontend state without a concrete reason.

---

# Routing

Use React Router according to the existing application structure.

Routes should be predictable and composable.

Do not put business logic directly into route configuration.

Route-level authorization should improve UX, but backend authorization remains authoritative.

---

# Components

Prefer small focused components.

A component should generally handle:

* rendering;
* user interaction;
* local UI state.

Complex domain operations should be handled through appropriate hooks/services/API abstractions.

Avoid putting large business workflows inside presentational components.

---

# Project workflow and Kanban

The backend provides the project's workflow through `ProjectStatus`.

The frontend must derive Kanban columns from project statuses.

Do not hardcode:

* status names;
* status IDs;
* number of columns;
* workflow order.

The conceptual structure is:

```text
Project
  └── ProjectStatus[]
        └── Task[]
```

A Kanban column represents one `ProjectStatus`.

Do not create a separate frontend domain concept that implies an independent backend `KanbanColumn` entity.

---

# Kanban ordering

There are two independent ordering concepts:

1. Project status order.
2. Task order within a status.

Do not mix them.

Changing task order must not change status order.

Moving a task to another status must preserve the project's workflow.

Use the backend API as the final authority for persisted ordering.

Optimistic UI updates may be used when appropriate, but failed mutations must be reconciled with the server state.

---

# Column resizing

Kanban column width is a user-specific preference.

Column width must not modify:

* ProjectStatus;
* workflow order;
* task status;
* project configuration.

Persist column-width preferences using the appropriate user/project settings mechanism when persistence is required.

Do not store user-specific UI preferences in project-wide workflow configuration.

---

# Forms

Forms should:

* provide clear validation feedback;
* show loading states;
* handle server-side validation errors;
* prevent duplicate submissions where appropriate;
* preserve accessible labels and controls.

Do not rely solely on client-side validation.

---

# Loading and errors

Every asynchronous UI operation should have an appropriate state for:

* loading;
* success;
* empty result;
* error.

Errors returned by the backend should be displayed in a user-understandable way.

Do not expose raw stack traces or internal backend details.

---

# Search and filters

Search and filtering should use backend APIs for server-side data.

Do not download an entire dataset to the browser solely to perform filtering when the backend supports the operation.

URL state may be used for shareable or navigable filters when appropriate.

Saved filters are persisted backend resources and must not be treated as purely local UI state.

---

# Notifications

Notifications are server-owned data.

The frontend is responsible for:

* displaying notifications;
* showing unread state;
* providing appropriate navigation;
* triggering relevant mutations.

Do not fabricate notification state that contradicts the backend.

---

# File uploads

Use the backend's file-upload contract.

Handle:

* upload progress where supported;
* validation errors;
* failed uploads;
* retry behavior where appropriate.

Do not assume that a successful browser-side upload means the backend operation has completed successfully.

---

# Accessibility

Interactive UI must be accessible.

Pay attention to:

* keyboard navigation;
* focus management;
* labels;
* semantic HTML;
* accessible names;
* dialogs;
* drag-and-drop alternatives.

Kanban interactions must have a usable non-drag interaction where appropriate.

---

# Testing

Frontend tests should focus on user-visible behavior and important domain interactions.

Depending on the change, test:

* rendering;
* user interaction;
* loading state;
* error state;
* successful mutation;
* authorization-related UI;
* Kanban behavior;
* status changes;
* task ordering;
* column resizing;
* filtering/search.

Avoid tests that merely duplicate implementation details.

For Kanban tests, verify that columns are derived from the provided project statuses rather than hardcoded values.

---

# Validation

For frontend changes, run the relevant configured checks.

Typical checks include:

```text
npm run lint
npm run typecheck
npm test
npm run build
```

Use the actual commands defined by the project.

Do not claim validation passed if the command was not actually run.

---

# Frontend completion checklist

Before considering a frontend task complete, verify:

* [ ] Backend API remains the source of truth.
* [ ] No workflow values are hardcoded.
* [ ] ProjectStatus is used as the Kanban column source.
* [ ] Server state and UI state are separated appropriately.
* [ ] Loading and error states are handled.
* [ ] Accessibility is considered.
* [ ] Relevant tests exist.
* [ ] Type checking passes.
* [ ] Linting passes.
* [ ] Build passes when relevant.
* [ ] No debug code remains.
