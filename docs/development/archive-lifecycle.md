# Archive lifecycle (TASK-035)

Organizations, projects and tasks use `archived_at`. Archive preserves task participants,
workflow/status references, board ordering, comments, file keys, links and history. An archived
object is read-only, including for the system administrator. Ready attachments remain downloadable
by authorized readers; pending attachments stay quarantined until the task and parents are active.

## User operations

Use **Archived organizations**, **Archived projects** or **Archived tasks** from the corresponding
management/board page. Archive lists are paginated. Task drawers expose Archive/Restore only when
allowed by backend capabilities. Confirmation is required for archiving and UI restoration.
Organization/project restoration explicitly warns about revoking previous memberships.

* Only the system administrator archives/restores organizations.
* The administrator and the organization's active managers archive/restore projects.
* Task lifecycle requires SA, scoped active OM/PM, or active project participation combined with
  matching `created_by`, `reporter_id` or `assignee_id`.
* Archive cascades to descendants and changes active memberships to archived, preserving roles.
  Previously revoked memberships remain revoked. Repeat authorized operations are no-ops.
* Restore parents first: organization → project → individual task. Restore never restores children.
  Restoring an organization revokes old organization and **all** its project memberships, including
  projects that stay archived; restoring a project revokes its old memberships. Roles become member.
* Add users again explicitly after restoring the corresponding scopes. Repeating restore on an
  already active object does not revoke new membership. Assignment IDs never change automatically.

Archived membership preserves only reads of archived objects in its former scope: OM globally,
PM within the organization, employee within the project. It does not raise the active global role.
Blocking/removing a user or restoring the membership's resource revokes this retained access.
Independent active grants continue to apply. Archive alone does not strike through an assignee;
blocked, missing or revoked required membership does, until the user is added again.

## Deployment and migration

Apply `0024_archive_lifecycle` after `0023_resource_descriptions` in the coordinated maintenance
window described in [the migration plan](../architecture/administration-migration.md).
Stop old API and writers, take coordinated database/file-storage backups, migrate with the trusted
migration role, then deploy the matching API, SPA and workers. The working database is not migrated
by development tests. This stage does not complete the TASK-028 release acceptance.

Migration renames organization/project `deleted_at` without changing timestamps, adds task archive
state, normalizes active legacy projects under archived organizations, and archives their tasks.
It preserves task timestamps/participants, workflow, links, history and storage references. Existing
membership state is reused; active memberships in archived scopes become archived, revoked rows
are not revived. Backfill emits no invented audit events. Downgrade explicitly refuses to lose task
archive state; use forward fixes or the coordinated pre-cutover backup recovery procedure.

Breaking API changes: resource lists are pages (`items`, `next_cursor`), responses expose
`archived_at` instead of `deleted_at`, and POST archive replaces resource DELETE (now 404).
Deploy API and SPA together. Restore paths are unchanged but now invalidate former membership.

## Transactions and background processing

Archive/restore uses exclusive transaction advisory lock `administration_lifecycle` (240031).
Task/workflow/chat changes and notification/scanner/manual-review work use its shared mode before
resource/storage locks and recheck current state. A failed audit insert rolls back the cascade.
Each actually archived object receives one administrative event sharing an operation ID;
restore records only the restored object. Automatic membership transitions create no separate
administrative events or fake TaskHistory. Existing technical resource lifecycle events remain
in SecurityEvent, separately from the administrative journal.

Deadline processing excludes archived tasks and parents. Scanner skips pending files under archived
objects; manual review rejects them. No archive notification queue is created or replayed. Existing
notifications remain stored and are returned only under current task/link read authorization.

Validation commands and coverage: [testing](testing.md#archive-lifecycle-task-035).
