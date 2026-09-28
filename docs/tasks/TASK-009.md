# TASK-009: Backend permission tests and Python 3.13 validation

## Goal

Закрепить permission-сценарии TASK-007 автоматизированными backend-тестами и обеспечить воспроизводимый запуск полного backend test suite в Python 3.13 окружении.

---

## Context

TASK-007 уже добавляет `reporter_id`, `assignee_id`, watchers и in-app notifications. Базовый API-тест покрывает основной happy path, но не фиксирует все границы доступа, изоляцию организаций и отрицательные сценарии.

Локальный системный Python может быть версии 3.10, тогда как backend требует Python `>=3.13`. Проверка должна выполняться в том же классе окружения, которое используется Dockerfile и CI.

---

## Requirements

### Functional requirements

* Проверить права владельца проекта, постановщика, текущего исполнителя и обычного участника.
* Проверить назначение исполнителя, self-assignment, замену и снятие исполнителя.
* Проверить смену постановщика только постановщиком или владельцем проекта.
* Проверить добавление и удаление наблюдателей согласно правилам TASK-007.
* Проверить идемпотентность повторного добавления наблюдателя.
* Проверить автоматическое добавление organization user в project members при назначении watcher.
* Проверить сохранение project membership после удаления watcher.
* Проверить изоляцию другой организации для reporter, assignee, watcher и notification.
* Проверить уведомления для всех требуемых типов изменений и read-on-open поведение.

### Technical requirements

* Использовать pytest, pytest-asyncio, httpx и SQLite test fixture из существующего backend stack.
* Запускать тесты в Python 3.13.
* Не использовать реальную PostgreSQL, Redis, MinIO или внешнюю сеть для unit/API tests.
* Зафиксировать команду воспроизводимого запуска через Docker или проектное Python 3.13 окружение.
* Не ослаблять текущие authorization checks и не подменять негативные сценарии проверками реализации.
* Не добавлять продуктовые изменения, не требуемые покрытием тестами.

---

## Acceptance Criteria

The task is considered functionally complete when:

* [x] Обычный участник не может менять assignee существующей задачи.
* [x] Участник может назначить себя исполнителем только при пустом assignee.
* [x] Владелец и текущий исполнитель могут менять или снимать assignee.
* [x] Обычный участник не может менять reporter.
* [x] Reporter и владелец проекта могут менять reporter.
* [x] Пользователь другой организации не может быть reporter, assignee или watcher.
* [x] Пользователь другой организации и пользователь без доступа к проекту не получают данные задачи или её watchers.
* [x] Участник может добавить и убрать себя из watchers.
* [x] Владелец и текущий исполнитель могут управлять watcher другого пользователя.
* [x] Повторное добавление watcher не создаёт дубль и не возвращает ошибку.
* [x] Organization user, добавленный watcher, автоматически становится project member.
* [x] Удаление watcher не удаляет project membership.
* [x] Уведомления создаются для status, assignee, reporter, title и description changes.
* [x] Actor не получает лишнее уведомление о собственном изменении, если это правило сохранено текущим контрактом.
* [x] Список уведомлений и unread count изолированы по recipient.
* [x] Открытие уведомления помечает его прочитанным, повторное открытие не меняет unread count.
* [x] Полный backend test suite проходит в Python 3.13.

---

## Domain

Задача не изменяет доменные сущности. Тесты закрепляют следующие инварианты:

* `created_by` остаётся техническим автором.
* `reporter_id` и `assignee_id` принадлежат организации проекта.
* В задаче не более одного assignee.
* Watcher не дублируется на одной задаче.
* Удаление watcher не удаляет `ProjectMember`.
* Notification доступна только её recipient.

---

## Architecture

Затрагиваются:

* backend API tests;
* test fixtures и helpers;
* Python 3.13 validation environment;
* при необходимости документация команды запуска.

Production backend, frontend, API contract и database schema не изменяются.

---

## API

Тесты покрывают существующие endpoints:

```text
POST  /api/projects/{project_id}/tasks
GET   /api/tasks/{task_id}
PATCH /api/tasks/{task_id}
GET   /api/tasks/{task_id}/watchers
POST  /api/tasks/{task_id}/watchers
DELETE /api/tasks/{task_id}/watchers/{user_id}
GET   /api/notifications
GET   /api/notifications/unread-count
POST  /api/notifications/{notification_id}/open
```

API-контракт менять не требуется.

---

## Database

Изменения схемы не требуются. Тесты используют существующие модели и миграцию TASK-007.

### Migration

* [ ] Yes
* [x] No

---

## Authorization

Тесты должны проверять:

* authentication и отсутствие доступа без bearer token;
* project membership и organization boundary;
* object-level authorization по task ID и notification ID;
* права project owner, reporter, assignee и regular member;
* отсутствие раскрытия существования объектов через чужие organization/project/task IDs.

---

## Frontend

Frontend-код не изменяется. Разрешены только изменения frontend-документации, если команда запуска backend validation должна быть явно описана в общем setup.

---

## Tests

### Backend

* [x] Unit tests
* [x] Integration tests
* [x] API tests
* [x] Authorization tests

### Frontend

* [ ] Component tests
* [ ] Interaction tests
* [ ] API/state tests

### Regression

* [x] Regression test required

Specific scenarios:

* owner/reporter/assignee/member permission matrix;
* cross-organization participant assignment;
* cross-project task and watcher access;
* watcher idempotency and membership retention;
* notification recipient isolation;
* read-on-open idempotency;
* migration-backed test schema creation;
* complete `pytest` run in Python 3.13.

---

## Dependencies

* `TASK-007` — participant and notification backend behavior.
* `TASK-003` — organization/project membership and authorization.
* `TASK-004` — task history and project workflow access.

---

## Validation

Recommended Docker-based validation:

```text
docker run --rm -v "$PWD/backend:/app" -w /app python:3.13-slim sh -lc \
  'pip install -e ".[dev]" && pytest -q'
```

Additional checks:

```text
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

The final report must include the exact Python version and commands that passed.

---

## Definition of Done

* [x] Requirements implemented as automated tests.
* [x] All acceptance criteria satisfied.
* [x] Positive, negative, authorization and isolation scenarios covered.
* [x] Tests are independent and use isolated database fixtures.
* [x] Full backend pytest suite passes in Python 3.13.
* [x] Ruff format, Ruff lint and mypy pass in the validated environment.
* [x] No database migration or API contract changes introduced.
* [x] Documentation updated if the validation command changes.
* [x] Final diff reviewed.

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
