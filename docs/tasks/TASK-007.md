# TASK-007: Task participants and in-app notifications

## Goal

Добавить в задачу постановщика, одного исполнителя и список наблюдателей, а также in-app уведомления о значимых изменениях задачи.

## Context

В текущей модели `Task` есть `created_by`, который является техническим автором создания записи. Для продуктовой роли постановщика требуется отдельное поле `reporter_id`. Исполнитель и наблюдатели должны быть связаны с пользователями организации и учитываться при работе с задачей и Kanban-интерфейсом.

TASK-005 использует эти данные на карточке и в боковой панели задачи.

References:

* `AGENTS.md`
* `backend/AGENTS.md`
* `frontend/AGENTS.md`
* `docs/product/requirements.md`
* `docs/product/glossary.md`
* `docs/architecture/overview.md`
* `docs/architecture/api.md`
* `docs/tasks/TASK-005.md`

## Requirements

### Functional requirements

* Добавить задаче одного постановщика (`reporter_id`).
* Сохранить `created_by` как технического автора создания записи.
* Добавить задаче одного исполнителя (`assignee_id`), допускающего отсутствие исполнителя.
* Добавить несколько наблюдателей.
* Постановщика и исполнителя можно выбирать только среди пользователей организации проекта.
* Если задача создаётся без исполнителя, любой участник проекта может назначить себя исполнителем.
* Назначать или менять исполнителя может владелец проекта или текущий исполнитель.
* Если исполнитель отсутствует, любой участник проекта может назначить себя.
* Постановщика может менять текущий постановщик или владелец проекта.
* Любой участник проекта может добавить или убрать себя из наблюдателей.
* Исполнитель и владелец проекта могут добавлять и удалять наблюдателей.
* Наблюдателем может быть любой пользователь организации проекта.
* Если наблюдатель ещё не является участником проекта, он автоматически добавляется в проект. После удаления наблюдения он остаётся участником проекта.
* Наблюдатели получают in-app уведомления о смене статуса, исполнителя, постановщика и изменениях задачи.
* В приложении должен быть список уведомлений и unread-счётчик.
* Открытие отдельного уведомления автоматически помечает его прочитанным.
* Уведомления не отправляются по email в рамках этой задачи.

### Technical requirements

* Использовать отдельные сущности/связи для reporter, assignee, watchers и notifications.
* Сохранить инварианты организации и проекта на backend.
* Пользователь, выбранный в reporter/assignee/watchers, должен принадлежать организации проекта.
* Нельзя назначить исполнителем, постановщиком или наблюдателем пользователя из другой организации.
* Нельзя получить или изменить наблюдателей, исполнителя, постановщика или уведомления через чужой project/task ID.
* Операции изменения участников задачи должны быть атомарными и проверять актуальное состояние прав на backend.
* Уведомление должно ссылаться на задачу и хранить получателя, тип события, текст/данные события, время создания и состояние прочитанности.
* Дублирование одинакового наблюдателя на одной задаче должно быть идемпотентным.
* Удаление наблюдателя не удаляет его из `ProjectMember`.

### Out of scope

* Email, push и внешние каналы уведомлений.
* Несколько исполнителей у одной задачи.
* Полноценная матрица ролей проекта.
* Автоматическое удаление пользователя из проекта после снятия наблюдения.

## Acceptance Criteria

* [ ] Новая задача получает `reporter_id` и сохраняет `created_by`.
* [ ] Для задачи можно назначить не более одного исполнителя или оставить исполнителя пустым.
* [ ] Reporter и assignee выбираются только из пользователей организации проекта.
* [ ] Пользователь из другой организации не может быть reporter, assignee или watcher.
* [ ] Участник проекта без исполнителя может назначить себя.
* [ ] Не-владелец и не-текущий исполнитель не могут менять исполнителя.
* [ ] Текущий постановщик может изменить постановщика.
* [ ] Владелец проекта может изменить постановщика.
* [ ] Другой участник проекта не может изменить постановщика.
* [ ] Участник проекта может добавить себя в наблюдатели.
* [ ] Участник проекта может убрать себя из наблюдателей.
* [ ] Исполнитель может управлять наблюдателями задачи.
* [ ] Владелец проекта может управлять наблюдателями задачи.
* [ ] Пользователь организации, не являющийся project member, при добавлении наблюдателем автоматически становится project member.
* [ ] После снятия наблюдения пользователь остаётся project member.
* [ ] Повторное добавление наблюдателя не создаёт дубль и не приводит к ошибке.
* [ ] Наблюдатели получают уведомление о смене статуса.
* [ ] Наблюдатели получают уведомление о смене исполнителя.
* [ ] Наблюдатели получают уведомление о смене постановщика.
* [ ] Наблюдатели получают уведомление об изменениях задачи.
* [ ] Уведомления доступны в списке пользователя и имеют unread-счётчик.
* [ ] Открытие уведомления автоматически помечает его прочитанным.
* [ ] Повторное открытие прочитанного уведомления не увеличивает unread-счётчик.
* [ ] Операции из другой организации или проекта возвращают корректную ошибку и не раскрывают данные.

## Domain

Relevant entities:

* `User`
* `Organization`
* `OrganizationMember`
* `Project`
* `ProjectMember`
* `Task`
* `Notification`
* `TaskWatcher`

Relevant task fields:

* `created_by` — технический автор создания записи; не заменяет постановщика.
* `reporter_id` — пользователь, ответственный за постановку задачи.
* `assignee_id` — единственный текущий исполнитель или `NULL`.

Relevant invariants:

* `reporter_id` и `assignee_id`, если заданы, принадлежат организации проекта.
* Каждый watcher принадлежит организации проекта.
* На одной задаче один пользователь присутствует в списке наблюдателей не более одного раза.
* Снятие наблюдения не меняет project membership.
* Уведомление принадлежит получателю и не может быть прочитано через чужой user ID.

## Architecture

Affected areas:

* Backend task model, repositories, services, schemas and authorization.
* Alembic migration for reporter/assignee and watcher/notification persistence.
* Task API for participant assignment and watcher management.
* Notification API for list, unread count and read-on-open.
* Frontend task drawer, task cards, watcher controls and notification list.

Recommended flow:

```text
HTTP request
    -> router
    -> schema validation
    -> task/project authorization
    -> service
    -> repository
    -> database
    -> notification creation in the same transaction
```

## API

The exact route names may follow existing project conventions, but the following operations are required.

### Task participants

```http
POST  /api/projects/{project_id}/tasks
PATCH /api/tasks/{task_id}
GET   /api/tasks/{task_id}
```

Task responses must expose:

```json
{
  "created_by": "user-uuid",
  "reporter_id": "user-uuid",
  "assignee_id": "user-uuid-or-null",
  "watchers": [
    {"id": "user-uuid", "email": "user@example.com"}
  ]
}
```

Participant changes may use task update fields or dedicated endpoints. The implementation must keep authorization explicit and avoid accepting organization/project IDs from the client as authority.

### Watchers

```http
GET    /api/tasks/{task_id}/watchers
POST   /api/tasks/{task_id}/watchers
DELETE /api/tasks/{task_id}/watchers/{user_id}
```

The add operation is idempotent. A self-service request may omit `user_id`; management requests must be limited to the project owner or current assignee.

### Notifications

```http
GET  /api/notifications
GET  /api/notifications/unread-count
POST /api/notifications/{notification_id}/open
```

Opening a notification marks it as read and returns the notification representation. Notification list access is restricted to the authenticated recipient.

### Errors

* `401 Unauthorized` — missing or invalid authentication.
* `403 Forbidden` — caller lacks project/task permission for the requested operation.
* `404 Not Found` — task, user, notification or project is outside the caller's visible boundary.
* `409 Conflict` — invalid participant state or conflicting assignment.
* `422 Unprocessable Entity` — malformed request.

## Database

### Changes

* Add nullable `tasks.assignee_id` with a foreign key to `users.id`.
* Add non-null `tasks.reporter_id` with a foreign key to `users.id`. Existing rows must be backfilled from `created_by`.
* Add `task_watchers(task_id, user_id, created_at)` with a unique composite key.
* Add `notifications` with recipient, task reference, event type, event payload/message, `created_at` and nullable `read_at`.
* Add indexes for task participant lookup and recipient unread notifications.
* Define explicit delete behavior and preserve task data integrity.

### Migration

A new Alembic migration is required:

* [x] Yes
* [ ] No

Migration considerations:

* Existing tasks receive `reporter_id = created_by`.
* Existing tasks have no assignee and no watchers.
* Notification migration must not fabricate historical notifications.

## Authorization

* All operations require an authenticated user.
* Task access requires project membership and active organization/project state.
* Reporter and assignee candidates must be organization members.
* Setting assignee: project owner or current assignee; when assignee is empty, any project member may assign themselves.
* Setting reporter: current reporter or project owner.
* Managing watchers: the watcher may add/remove self; current assignee and project owner may manage any watcher.
* Adding an organization user as watcher automatically adds project membership and never removes it on unwatch.
* Notification list and read operations are restricted to the notification recipient.
* Every lookup must verify the task/project boundary to prevent IDOR.

## Frontend

* Extend the task card with reporter, assignee and watcher indicators where appropriate.
* Add participant controls to the task drawer.
* Allow an eligible user to assign themselves when a task has no assignee.
* Show watcher list and self-service watch/unwatch action.
* Show management controls only when backend/user state allows them, while handling rejected mutations from the backend.
* Add notification list and unread counter to the authenticated workspace.
* Opening a notification marks it read and navigates to the related task drawer when the task is accessible.
* Provide loading, empty, error and mutation states.

## Tests

### Backend

* [ ] Model and migration tests for reporter/assignee/watcher/notification constraints.
* [ ] API tests for participant assignment and replacement.
* [ ] Authorization tests for project owner, reporter, assignee and regular member.
* [ ] Organization isolation tests for all participant operations.
* [ ] Idempotency tests for watcher addition.
* [ ] Membership retention tests after unwatch.
* [ ] Notification creation tests for each required event.
* [ ] Notification recipient isolation and read-on-open tests.

### Frontend

* [ ] Component tests for participant controls and notification list.
* [ ] Interaction tests for self-assignment, watcher management and read-on-open.
* [ ] API/state tests for participant mutations and notification unread count.

### Regression

* [ ] Existing task creation/update, project membership and Kanban flows remain functional.
* [ ] Existing history events remain attributable to `created_by`/actor and are not rewritten as notifications.

## Dependencies

* `TASK-001` — core task domain.
* `TASK-002` — authentication.
* `TASK-003` — organization/project membership and authorization.
* `TASK-004` — task history and Kanban API.
* `TASK-005` — Kanban task drawer and frontend integration.

## Validation

```bash
# Backend
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app

# Frontend
cd frontend
npm run build
npm run lint
npm run test

# Other
# Verify notification and participant flows through Docker Compose.
```

## Definition of Done

* [ ] Requirements implemented.
* [ ] Acceptance criteria satisfied.
* [ ] Domain invariants preserved.
* [ ] Authorization implemented and tested.
* [ ] Database migration created and verified.
* [ ] API contract updated.
* [ ] Relevant backend and frontend tests added or updated.
* [ ] Relevant validation passed.
* [ ] Documentation updated when required.
* [ ] Final diff reviewed.
* [ ] No unrelated changes introduced.

## Implementation Notes

* Keep `created_by` as the technical creator and introduce `reporter_id` as a separate product field.
* Use organization membership as the candidate boundary for reporter and assignee.
* Do not remove project membership when a user stops watching a task.
* Generate notifications transactionally from successful task changes.
* Keep notification event types explicit and stable for frontend rendering.

## Status

* Status: TODO
* Started:
* Completed:

### Progress

* [ ] Analysis
* [ ] Implementation
* [ ] Tests
* [ ] Validation
* [ ] Review

### Known issues

* None.
