# Administration release: installation, cutover and recovery (TASK-038)

Current schema: `0025_email_change`. API, SPA and **all four workers** must use the same
reviewed source revision. TASK-038 prepares and rehearses deployment; it does not authorize
updating a shared database or publishing a release. See the [acceptance record](administration-validation.md)
for actual results and outstanding gates. Do not deploy while a required gate is unresolved.

## Compatibility and preparation

The release replaces ownership with scoped manager/member roles, removes registration,
password recovery and self-deactivation, adds archive states and entity audit. Old clients
must reload and sign in again. Existing permanent passwords survive except for the selected
configuration administrator. Set nonempty `ADMIN_EMAIL` / `ADMIN_PASSWORD` identically for
all processes; no `TRACKER_` prefix. Choose the intended administrator explicitly: bootstrap
can unblock that account, replace its password and remove the previous system role.

Record the old/new application revisions and image digests, `alembic current`, database and
bucket names, counts and manifests before maintenance. Keep old configuration/secrets privately
with the backup, never in the repository or acceptance logs. Rehearse on a disposable restored
copy first. Allow time for database backup/restore, owner backfill, cascades and ClamAV startup.
There is no online mixed-version upgrade or guaranteed duration independent of data size.

For pre-0016 bytea installations, first use the [attachment transfer procedure](attachments.md#existing-installations-explicit-cutover)
at revision `0015_attachment_objects`. Verify object hashes before advancing. For existing
0018 installations, apply the linear chain 0019 → 0020 → 0021 → 0022 → 0023 → 0024 → 0025.
Do not edit applied migrations, stamp head, disable audit triggers or run old workers between steps.

## Database identities

The default Compose database credential is an owner/superuser convenience for local development.
It does **not** provide the ADR-013 runtime security boundary. Shared installations require:

* a trusted migration identity owning schema/tables/functions;
* a distinct runtime login for API and every worker, without superuser, ownership, role
  inheritance, DDL, replication-setting or trigger-disabling privileges;
* `TRACKER_DATABASE_URL` pointing to the runtime identity in the private deployment environment;
* the supplied [runtime override](../../deploy/compose.runtime.yml), which removes automatic
  migrations from API startup. Run migrations once, separately, before replicas start.

As the database owner, provision the role (adapt names to the installation):

```sql
CREATE ROLE tracker_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
-- In interactive psql, use \password tracker_runtime; do not put the password in this file.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE tracker TO tracker_runtime;
GRANT USAGE ON SCHEMA public TO tracker_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO tracker_runtime;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO tracker_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO tracker_runtime;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO tracker_runtime;
```

Run default-privilege commands as the actual migration/table owner, for every relevant owner.
The runtime must not be a member of that role or own another writable schema. Verify with
`current_user`, `pg_roles`, table/function owners and schema privileges. Grant no TRUNCATE.
Append-only ALWAYS triggers still reject UPDATE/DELETE/cascades on all three journals.
The rehearsal runs actual API/bootstrap/workers under this role and attempts prohibited DDL/DML.
Trusted DBA/backup operators remain outside this protection boundary; see [ADR-013](../architecture/decisions/013-audit-history-integrity.md).

## Maintenance and coordinated backup

Use an explicit Compose project/configuration for the intended installation. The examples below
assume its `.env`, database name `tracker` and owner `tracker`; adapt these before execution.
Enable maintenance at the ingress and drain requests. Stop all old API replicas, workers,
operator file jobs and any external writers. Keep the maintenance page independent of the SPA.

```sh
docker compose stop frontend backend deadline-worker registration-mail-worker attachment-scan-worker attachment-cleanup-worker
umask 077
mkdir -p backups/pre-administration
docker compose exec -T db pg_dump -U tracker -d tracker -Fc > backups/pre-administration/database.dump
docker compose exec -T db pg_dumpall -U tracker --globals-only > backups/pre-administration/globals.sql
docker compose config --images > backups/pre-administration/images.txt
# Stop MinIO before an offline filesystem copy, preserving internal metadata and all buckets.
docker compose stop minio
docker run --rm --volumes-from "$(docker compose ps -aq minio)":ro \
  -v "$PWD/backups/pre-administration:/backup" alpine:3.21 \
  tar -C /bitnami/minio/data -cpf /backup/minio.tar .
sha256sum backups/pre-administration/database.dump backups/pre-administration/minio.tar \
  > backups/pre-administration/SHA256SUMS
```

Store encrypted copies outside the host with restricted access. `globals.sql` may contain role
password hashes and is sensitive. Save deployment secrets separately with equally restricted
access. Never print `docker compose config` with expanded environment to a public log.

Restore-test into **new** database/storage resources, never into a populated database with
append-only journals. Start only the restored PostgreSQL and MinIO, using the same PostgreSQL
major and MinIO image. Use `pg_restore --exit-on-error --no-owner --no-acl` into the empty database
under its trusted owner; recreate reviewed roles/grants separately. Populate the new, stopped
MinIO volume from `minio.tar` at `/bitnami/minio/data`, preserving ownership, then start MinIO.
Check every referenced key, size and SHA-256, plus table counts and journal snapshots. Keep
cleanup stopped until the DB/bucket pair is confirmed. SQL alone does not contain file bytes.
The automated rehearsal also proves `pg_dump`/`pg_restore` of synthetic data and independent
bucket copy/hash verification; it is not a substitute for testing the installation's full volume backup.

## Migration and startup

Build the reviewed images without starting writers. Use the runtime override for every subsequent
Compose command. Supply the migration URL privately through the environment only for migration;
`MIGRATION_DATABASE_URL` below is an operator shell variable, not an application setting.

```sh
docker compose -f docker-compose.yml -f deploy/compose.runtime.yml build
docker compose up -d db redis minio
# Read privately; do not echo this variable or save it in command logs.
read -r -s -p 'Migration database URL: ' MIGRATION_DATABASE_URL
TRACKER_DATABASE_URL="$MIGRATION_DATABASE_URL" docker compose \
  -f docker-compose.yml -f deploy/compose.runtime.yml run --rm --no-deps backend alembic upgrade head
unset MIGRATION_DATABASE_URL
# Writers remain stopped. This revokes old sessions and adds atomic technical audit events.
docker compose exec -T db psql -U tracker -d tracker -v ON_ERROR_STOP=1 \
  < deploy/administration-cutover.sql
# Apply/check the runtime grants above after new tables exist.
docker compose -f docker-compose.yml -f deploy/compose.runtime.yml up -d --wait backend
```

[Cutover SQL](../../deploy/administration-cutover.sql) is an explicit trusted maintenance operation,
not an automatic migration or public endpoint. It uses lifecycle lock 240031, records each actual
session revocation in the same transaction, emits no passwords/tokens and is safe to repeat
before opening traffic. Migration 0022 invalidates old registration/reset queues. A signing-key
rotation alone is not a replacement for session revocation. Bootstrap with unchanged credentials
normally preserves sessions; it does not revoke every ordinary user's session at release time.

After migrations and bootstrap, verify head and postconditions before starting remaining services:

* known legacy owners mapped to manager memberships; blocked users gain no active grants;
* no active project grant without an active org grant, active user and active parents;
* legacy deleted timestamps normalized to archive states, with tasks under archived parents;
* task IDs, three participant IDs, workflow/status IDs/order, task timestamps, links, comments,
  notifications, object keys/size/hash and prior journal rows preserved;
* old sessions revoked, public registration/reset links rejected, required configuration present;
* a single configured system administrator, no implicit creator membership, correct capabilities.

```sh
docker compose -f docker-compose.yml -f deploy/compose.runtime.yml up -d --wait \
  frontend registration-mail-worker deadline-worker clamav attachment-scan-worker attachment-cleanup-worker
```

The historically named `registration-mail-worker` now delivers email-change confirmations and
cleans expired sessions; it never delivers registration/reset messages. ClamAV outages leave
files pending. Verify admin → organization → managers → employee → temporary password/change/
relogin → task/chat/file → block/revoke → archive → parent-first restore → explicit new memberships
→ entity audit. Check SMTP confirmation, download authorization and each worker's status.
Only after successful checks remove maintenance and require old browser tabs to reload/relogin.

## Recovery and rollback limits

Prefer a forward fix after cutover. `alembic downgrade` cannot reconstruct owners, removed
registration/reset requests, old password hashes, revoked memberships, independent task archive
states or transferred bytea files. 0020/0021 and 0024 refuse unsafe downgrade; nonempty 0019 refuses
journal loss. Downgrading 0025 discards pending email confirmations, not sent mail.

To return to the previous application, stop/drain **all** writers again, preserve the current
DB/MinIO pair separately, then restore the verified pre-cutover DB **and** MinIO backup into
fresh resources with the old images/configuration. Review role ownership/grants before startup.
Changes since that checkpoint are lost unless separately reconciled by an operator; no automatic
merge is provided. Do not restore over existing journals, truncate them, drop their triggers,
start cleanup with a mismatched bucket, or promise one downgrade recovers deleted information.
