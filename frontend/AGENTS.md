# Frontend Agent Instructions

This file contains frontend-specific rules.

The root `AGENTS.md` remains authoritative for project-wide
architecture, domain rules, security and Definition of Done.

---

# 1. Frontend responsibility

The frontend is responsible for:

- user interface;
- navigation;
- forms;
- Kanban board;
- task views;
- project views;
- filters;
- notifications UI;
- client-side interaction;
- presentation state.

The frontend is NOT the source of truth for business rules.

Backend API is authoritative.

---

# 2. Technology

Use:

- TypeScript
- React
- Vite
- React Router
- TanStack Query
- ESLint
- strict TypeScript

Use existing project dependencies before adding new libraries.

---

# 3. Expected structure

Expected structure:

    frontend/
    ├── src/
    │   ├── app/
    │   ├── components/
    │   ├── features/
    │   ├── pages/
    │   ├── api/
    │   ├── hooks/
    │   ├── lib/
    │   └── types/
    │
    └── tests/

The exact structure may evolve.

Do not reorganize the whole frontend
for a single feature.

---

# 4. TypeScript

Use strict TypeScript.

Do not use:

    any

unless there is a documented technical reason.

Prefer:

- explicit types;
- generated API types;
- discriminated unions;
- reusable domain types.

Avoid duplicated interfaces when the API contract already provides
the required type.

---

# 5. Backend API is authoritative

Frontend must follow the backend API contract.

Do not invent endpoints.

Do not assume response fields that are not documented.

Do not silently transform API semantics.

If the frontend needs data that the backend does not provide,
identify the API gap instead of inventing client-side state.

---

# 6. API client

Prefer the project's configured API client.

If OpenAPI-generated types/client are available,
use them instead of manually duplicating endpoint definitions.

Do not create multiple API clients for the same backend.

---

# 7. Server state

Server state should use the configured query/data-fetching layer.

Examples:

- project;
- project statuses;
- tasks;
- comments;
- watchers;
- filters.

Do not copy server data into multiple independent React states
without a concrete reason.

Avoid manually implementing a second caching system.

---

# 8. Local UI state

Local state is appropriate for:

- modal visibility;
- input values;
- temporary drag state;
- expanded/collapsed UI;
- column resizing before persistence;
- purely visual preferences.

Do not use local state as a replacement for server state.

---

# 9. Authentication

Frontend may know whether a user appears authenticated,
but backend authorization remains authoritative.

Do not hide security behind UI conditions.

For example:

    if (!canEdit) {
        hideButton();
    }

is useful UX,

but backend must still reject:

    PATCH /tasks/{id}

when the user lacks permission.

---

# 10. Authorization UI

Permission-aware UI should improve user experience.

Examples:

- hide unavailable actions;
- disable controls;
- show permission errors.

However, never assume that hidden UI is security.

Every protected operation must be enforced by backend.

---

# 11. Project workflow

The frontend must treat ProjectStatus as dynamic data.

Example API result:

    statuses = [
        {
            id: "...",
            name: "Backlog",
            position: 0
        },
        {
            id: "...",
            name: "Development",
            position: 1
        }
    ]

Render these values dynamically.

Never hardcode:

    Backlog
    Todo
    In Progress
    Done

as the universal workflow.

---

# 12. Kanban

Kanban columns are derived from ProjectStatus.

Conceptually:

    Project
       ↓
    ProjectStatus[]
       ↓
    KanbanColumn[]

The frontend may create a view-model
for rendering, but it must not create an independent workflow model.

---

# 13. Kanban ordering

Column order comes from backend data.

Task order comes from task position/order data.

Do not use:

- database ID;
- array insertion order;
- task creation timestamp

as a substitute for explicit ordering
when the API provides an order field.

---

# 14. Drag and drop

Moving a task should result in an API operation.

Conceptually:

    drag task
        ↓
    determine target status
        ↓
    call backend
        ↓
    update/query invalidation
        ↓
    render server state

The backend decides whether the operation is valid.

---

# 15. Optimistic updates

Optimistic UI updates are allowed
when they improve user experience.

However:

- rollback must be implemented;
- failed API calls must be visible;
- server state must eventually be synchronized.

Do not leave the UI in an optimistic state after a failed request.

---

# 16. Column resizing

Kanban column width is a user preference.

Do not modify ProjectStatus to store user-specific width.

Conceptually:

    ProjectStatus
        ↓
    shared workflow

    User + Project + Status
        ↓
    personal column width

Column width should be persisted through the appropriate backend API
when persistence is supported.

---

# 17. Forms

Forms should:

- provide immediate useful validation;
- show server validation errors;
- prevent accidental duplicate submissions;
- clearly indicate loading state.

Frontend validation improves UX.

Backend validation remains authoritative.

---

# 18. Error handling

UI must explicitly handle:

- loading;
- success;
- empty;
- error;
- unauthorized;
- forbidden;
- not found.

Avoid generic messages such as:

    "Something went wrong"

when a useful API error can be displayed.

Do not expose internal backend stack traces.

---

# 19. Loading states

Every async user operation should have an understandable state.

Examples:

- loading spinner;
- skeleton;
- disabled submit button;
- progress indication;
- optimistic state.

Do not allow repeated clicks to trigger duplicate operations
unless the API operation is intentionally idempotent.

---

# 20. Components

Prefer focused components.

Good:

    TaskCard
    KanbanColumn
    TaskEditor
    ProjectHeader
    StatusSettings

Avoid huge components containing all project functionality.

If a component becomes difficult to understand,
split it by responsibility.

---

# 21. Business logic

Do not duplicate backend business rules.

Bad:

    if (statusName === "Done") {
        ...
    }

when the behavior actually depends on configurable project workflow.

Prefer explicit API data such as:

    status.is_final

if such domain behavior is required.

Display names must not be used as stable identifiers.

---

# 22. Accessibility

Interactive UI must be accessible.

Use:

- semantic HTML;
- labels;
- keyboard interaction;
- focus management;
- accessible names;
- appropriate ARIA attributes.

Drag-and-drop functionality must have a usable keyboard or
alternative interaction where practical.

Do not make essential functionality mouse-only.

---

# 23. Routing

Use the project's configured router.

Routes should correspond to product concepts.

Examples:

    /projects
    /projects/:projectId
    /projects/:projectId/board
    /projects/:projectId/tasks/:taskId

Do not duplicate routing mechanisms.

---

# 24. URL state

Use URL parameters/query parameters when state should be:

- shareable;
- bookmarkable;
- restorable after reload.

Examples:

- project;
- filters;
- search;
- selected task;
- board view.

Do not keep shareable navigation state only in React memory.

---

# 25. Search and filters

The backend performs actual search/filtering.

Frontend sends filter parameters to the API.

Do not fetch the complete task database
and perform large-scale filtering in JavaScript.

---

# 26. Saved filters

Saved filters are server-side entities.

The frontend should treat them as API resources.

Do not store saved filters only in localStorage.

Local UI preferences may use localStorage
when the product explicitly defines them as local.

---

# 27. Notifications

Notifications should reflect server state.

The frontend should not invent notification events.

Handle:

- unread state;
- loading;
- pagination;
- marking read;
- errors.

---

# 28. File uploads

File uploads must follow backend constraints.

Frontend may validate:

- size;
- type;
- filename;

for user feedback.

Backend must validate again.

Do not assume MIME type supplied by the browser is trustworthy.

---

# 29. Tests

Test observable behavior.

Important scenarios:

- project loads;
- statuses load;
- Kanban renders dynamic columns;
- tasks appear in correct columns;
- task can be moved;
- failed move rolls back;
- task creation works;
- validation errors appear;
- permission errors appear;
- filters update results.

Avoid tests that depend heavily on component internals.

---

# 30. Frontend Definition of Done

Before reporting completion:

    make lint
    make typecheck
    make test-frontend
    make build-frontend

The agent must report which commands were actually executed.

Never claim a check passed if it was not executed.
