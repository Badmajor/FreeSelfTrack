# ADR-004: Explicit ownership and soft-deleted resource lifecycle

## Status

Accepted

## Context

Organizations and projects need membership management with a small, explicit permission model. The product also requires destructive actions to be reversible and to preserve project data.

Membership alone is not sufficient to represent ownership because an owner must remain distinguishable from ordinary members and ownership must be unique.

## Decision

Organizations and projects store ownership in separate non-null `owner_id` foreign keys to `users.id`.

* Only the organization owner manages organization membership and organization ownership transfer.
* Only the project owner manages project membership, project ownership transfer, and project deletion/restoration.
* Ownership transfer targets an existing member identified by email.
* Membership creation is idempotent.
* Organizations and projects use `deleted_at` soft deletion. Normal access and list queries exclude deleted resources.
* Deletion requires an explicit `{ "confirm": true }` request body.
* Organization soft deletion marks the organization and its projects deleted without removing their data.
* Restoring an organization does not restore projects. A project can be restored separately only after its organization is active.

## Consequences

* Ownership rules are straightforward to enforce in services and database constraints.
* Existing membership rows require a deterministic owner backfill in the migration.
* Queries must consistently filter deleted organizations and projects.
* Data is retained for restoration, so physical cleanup is outside this task.
* The frontend can provide owner-only controls, but the backend remains authoritative.
