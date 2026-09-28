# TASK-005: Kanban frontend

## Goal

Добавить desktop-интерфейс Kanban в существующий workspace с организациями и проектами, используя backend API TASK-004.

## Context

Backend уже предоставляет доску проекта, независимую cursor-based пагинацию колонок, перемещение задач и историю переходов. Frontend должен отображать эти данные без дублирования workflow-логики и открываться отдельным действием из текущего workspace.

References:

* `frontend/AGENTS.md`
* `docs/product/requirements.md`
* `docs/product/glossary.md`
* `docs/architecture/api.md`
* `docs/tasks/TASK-004.md`

## Requirements

### Functional requirements

* Сохранить текущий workspace с выбором организации и проекта.
* Добавить отдельное действие для открытия Kanban выбранного проекта.
* Строить колонки только из статусов, возвращённых backend API.
* Перемещать задачи drag-and-drop между активными колонками.
* Предоставить альтернативную смену статуса через меню на карточке или в боковой панели задачи.
* Загружать следующую страницу задач независимо для каждой колонки при прокрутке.
* Показывать на карточке название, идентификатор и дату обновления задачи.
* Предусмотреть отображение исполнителя после выполнения TASK-007.
* Показывать список наблюдателей и возможность добавить/убрать себя из наблюдателей.
* Открывать задачу в боковой панели поверх Kanban.
* В боковой панели разрешить редактирование названия и описания, смену статуса, просмотр истории и закрытие панели.
* Предусмотреть смену исполнителя после выполнения TASK-007.
* Предусмотреть управление наблюдателями по правилам TASK-007.
* Создавать задачу только из конкретной Kanban-колонки. Новая задача создаётся с выбранным статусом этой колонки.
* Позволить менять ширину колонок и сохранять настройки локально в браузере.
* Показывать loading, empty, success и error состояния для асинхронных операций.

### Out of scope

* Управление статусами проекта: создание, переименование, reorder, архивирование и восстановление.
* Mobile-адаптация Kanban. В рамках задачи поддерживается desktop.
* Backend-поддержка исполнителя; она входит в TASK-007.

### Technical requirements

* Использовать существующий TypeScript/React/Vite стек и настроенный API client.
* Использовать TanStack Query для server state, если он уже подключён или подключение необходимо для реализации API-состояния.
* Не размещать raw HTTP-запросы внутри Kanban-компонентов.
* Не хардкодить имена, идентификаторы, количество и порядок статусов.
* Использовать backend как источник истины после drag-and-drop и обычного обновления статуса.
* При ошибке mutation откатывать optimistic UI либо обновлять данные с backend.
* Cursor передавать как opaque value и не декодировать на frontend.
* Ограничить размер страницы значением backend API: максимум 500 задач на колонку.

## Acceptance Criteria

* [x] В текущем workspace есть действие открытия Kanban для выбранного проекта.
* [x] Kanban получает проект и активные колонки через `GET /api/projects/{project_id}/board`.
* [x] Названия, порядок и количество колонок полностью соответствуют ответу backend.
* [x] Карточка показывает название, идентификатор и дату обновления задачи.
* [x] Исполнитель отображается после интеграции TASK-007.
* [x] В задаче отображается список наблюдателей и доступно self-service добавление/удаление.
* [x] Задачу можно переместить drag-and-drop в другую активную колонку.
* [x] Статус задачи можно изменить через меню без drag-and-drop.
* [x] После успешного изменения статуса UI показывает состояние, подтверждённое backend.
* [x] Ошибка перемещения отображается пользователю, а UI синхронизируется с backend.
* [x] При прокрутке каждой колонки отдельно загружается только следующая страница этой колонки.
* [x] Cursor не дублируется и не пропускает задачи при последовательной загрузке страниц.
* [x] Для пустой колонки показывается понятное empty state.
* [x] Для загрузки и ошибки каждой колонки предусмотрены отдельные состояния.
* [x] Клик по карточке открывает боковую панель поверх Kanban.
* [x] Боковая панель позволяет изменить название и описание задачи.
* [x] Боковая панель позволяет сменить статус задачи.
* [x] Боковая панель показывает историю переходов задачи в порядке от новых к старым.
* [x] Боковая панель показывает постановщика, исполнителя и наблюдателей согласно TASK-007.
* [x] Боковую панель можно закрыть без потери состояния Kanban.
* [x] Новая задача создаётся из выбранной колонки и получает её статус.
* [x] Ошибки создания и редактирования отображаются без потери введённых данных.
* [x] Изменение ширины колонок работает на desktop и сохраняется в localStorage.
* [x] Настройка ширины является локальной для пользователя и не изменяет workflow проекта.
* [x] Управление статусами отсутствует в рамках TASK-005.
* [x] Mobile-адаптация не является критерием TASK-005.

## Domain

Relevant entities:

* `Project`
* `ProjectStatus`
* `Task`
* `TaskHistory`

Relevant invariants:

* Kanban column corresponds to exactly one backend `ProjectStatus`.
* Status order is the project workflow order returned by backend.
* Task status must belong to the same project as the task.
* Task order inside a column is independent from status order.
* Column width is a user-local visual preference and must not modify project workflow.

## Architecture

Affected areas:

* Frontend workspace navigation.
* Frontend API client and TypeScript domain types.
* Kanban page and focused components for board, column, task card, task drawer, history and task creation.
* TanStack Query server-state hooks/cache invalidation.
* Local browser storage for column widths.

The request flow remains:

```text
Workspace action -> Kanban route/view -> API client/query -> backend API
```

## API

TASK-005 consumes the API implemented by TASK-004. No backend endpoint is added in this task.

### Endpoints

```http
GET   /api/projects/{project_id}/board?limit=500
GET   /api/projects/{project_id}/board/columns/{status_id}/tasks?limit=500&cursor=...
POST  /api/projects/{project_id}/tasks
PATCH /api/tasks/{task_id}
GET   /api/tasks/{task_id}/history?limit=500&cursor=...
```

### Frontend behavior

* The initial board response supplies ordered columns and their first task pages.
* Each column stores and advances its own `next_cursor`.
* `PATCH /api/tasks/{task_id}` is used for status, title and description changes.
* The create-task request uses the selected column status ID.
* History is loaded for the task drawer and is not embedded into task cards.

### Errors

* `401`/`403`/`404`: show access or resource error and do not fabricate board data.
* `409`/`422`: show the backend validation message in a user-understandable form and reconcile server state.
* Network failure: preserve local form input and offer retry.

## Database

No database changes are required.

### Migration

A new Alembic migration is required:

* [ ] Yes
* [x] No

## Authorization

* Kanban access is available only to authenticated project members through backend authorization.
* Frontend route visibility improves UX but does not replace backend checks.
* Status configuration controls are not part of this task.
* Task mutation errors from backend must be handled without assuming the user has permission.

## Frontend

### Proposed components

* `Workspace`: existing organization/project selection and Kanban action.
* `KanbanView`: board-level query and layout.
* `KanbanColumn`: status header, task list, independent loading/error/empty state and load-more trigger.
* `TaskCard`: task summary and drag source.
* `TaskDrawer`: task editing, status menu, history and close behavior.
* `CreateTaskForm`: creation scoped to a selected column.

Names are implementation suggestions; follow the existing project structure if it differs.

### Interaction and accessibility

* Drag-and-drop must have a keyboard-accessible status change alternative.
* Buttons, menus, inputs and drawer controls require accessible names and focus handling.
* Opening the drawer should move focus into it; closing should return focus to the triggering task card.
* Loading and mutation states must prevent duplicate submissions and communicate progress.

## Tests

### Backend

* [x] No backend changes required.

### Frontend

* [x] Component tests for board, column, card, task drawer and create-task form.
* [x] Interaction tests for drag-and-drop and menu-based status changes.
* [x] API/state tests for independent cursors and query invalidation after mutations.
* [x] Error/loading/empty-state tests.
* [x] localStorage tests for column width persistence.
* [x] Accessibility test for keyboard status change and drawer focus behavior.

### Regression

* [x] Existing authentication and workspace flows remain functional.
* [x] Existing project/member management remains functional.
* [x] No project-wide workflow mutation is triggered by resizing columns.

## Dependencies

* `TASK-001` — core task domain.
* `TASK-002` — authentication.
* `TASK-003` — project membership and authorization.
* `TASK-004` — Kanban API, board pagination and task history.
* `TASK-007` — reporter, assignee, watchers, notifications and participant selection integration.

## Validation

```bash
# Frontend
cd frontend
npm run build
npm run lint
npm run test

# Other
# Verify Kanban through the Docker Compose frontend and backend.
# Verify desktop drag-and-drop, menu status changes, pagination, drawer, creation and localStorage width persistence.
```

## Definition of Done

* [x] Requirements implemented.
* [x] Acceptance criteria satisfied.
* [x] Domain invariants preserved.
* [x] Authorization handled through backend API and tested.
* [x] No database migration required.
* [x] API client and frontend types updated.
* [x] Relevant component and interaction tests added or updated.
* [x] Relevant validation passed.
* [x] Documentation updated when required.
* [x] Final diff reviewed.
* [x] No unrelated changes introduced.

## Implementation Notes

* Keep the existing workspace as the navigation context; Kanban is an action/view for the selected project.
* Treat cursors as opaque and keep pagination state per column.
* Store column widths in localStorage using a project/user-scoped key; never send them to project workflow endpoints.
* Reporter, executor, watcher display and participant selection are coupled to TASK-007.
* If executor support is not ready, do not invent an executor field or mock executor data in TASK-005.

## Status

* Status: DONE
* Started: 2026-09-28
* Completed: 2026-09-28

### Progress

* [x] Analysis
* [x] Implementation
* [x] Tests
* [x] Validation
* [x] Review

### Known issues

* None.
