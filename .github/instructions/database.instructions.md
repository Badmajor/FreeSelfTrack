
---
applyTo: "**/models/**/*.py,**/repositories/**/*.py,**/migrations/**/*.py,**/alembic/**/*,**/*migration*.py"
---

# Database Development Instructions

## Database

The primary database is PostgreSQL.

Use SQLAlchemy 2.x for database access.

Use Alembic for schema migrations.

## Models

Database models must represent persistent domain data.

Do not put complex business logic into SQLAlchemy models.

Use explicit relationships.

Define appropriate:

- primary keys;
- foreign keys;
- indexes;
- unique constraints;
- check constraints.

## Foreign keys

Deletion behavior must be explicit.

Do not rely on implicit database behavior.

Choose deliberately between:

- CASCADE;
- SET NULL;
- RESTRICT;
- NO ACTION.

Document non-obvious deletion semantics.

## Constraints

Important business invariants should be enforced at the database level when practical.

Examples:

- unique project key;
- unique user email;
- unique project status key;
- unique membership;
- unique task number within a project.

Do not rely exclusively on application-level checks for uniqueness.

## Indexes

Add indexes for fields frequently used in:

- filtering;
- joins;
- ordering;
- lookups.

Do not add indexes blindly.

Every index should have a practical query/use case.

## Migrations

Every schema change requires an Alembic migration.

Never modify an existing migration that may already have been applied to another environment.

Create a new migration instead.

Migration names must clearly describe the change.

Example:

```text
add_project_statuses
add_task_assignee
create_task_history
````

## Migration safety

Migrations must be reviewed for production safety.

Be especially careful with:

* large table rewrites;
* adding non-null columns;
* unique constraints;
* destructive operations;
* data migrations.

Do not silently delete or transform production data.

## Data migrations

If schema changes require existing data to be transformed:

1. explicitly document the transformation;
2. make the migration deterministic;
3. consider rollback implications;
4. test it against representative data.

## Queries

Keep database queries in repositories or dedicated data-access modules.

Do not place complex SQLAlchemy queries directly in API routers.

Avoid N+1 queries.

Use appropriate loading strategies.

## Transactions

Transaction boundaries must be explicit.

A service performing several related database operations should use an appropriate transaction.

Do not commit from multiple unrelated layers of the same operation.

## Soft deletion

If a domain entity requires archival rather than physical deletion, follow the project's established soft-delete approach.

Do not invent a different deletion strategy for a single feature.

## Tests

Database behavior that is important to business logic must have integration tests.

Test:

* constraints;
* relationships;
* cascade/restrict behavior;
* migrations where appropriate;
* important queries.

## Project-specific domain rule

Project owns its workflow.

The relationship is:

```text
Project
    ↓
ProjectStatus
    ↓
Task
```

`ProjectStatus` must not become a global status shared by unrelated projects.

Kanban columns are a presentation of the project's statuses.

Do not create a separate `KanbanColumn` entity unless explicitly required by a future architecture decision.
