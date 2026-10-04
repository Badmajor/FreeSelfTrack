# Attachment storage operations (TASK-024 / TASK-026 / TASK-027)

## Startup

MinIO uses the existing pinned `openvidu/minio` image, existing credentials and `minio_data`
volume. Compose sets `MINIO_DEFAULT_BUCKETS=${S3_BUCKET:-tracker-attachments}` and preserves
the image's default startup command. The volume mounts at `/bitnami/minio/data`, the image's
writable default directory; its existing contents remain at the volume root. No separate
`minio-init`, `minio-provision`, application identity/policy or lifecycle rule is created.
Do not restore the former `server /data` command: that bypasses native bucket initialization.

Set MINIO_ROOT_USER/MINIO_ROOT_PASSWORD and S3_BUCKET in `.env`. Backend and attachment workers
receive those credentials as TRACKER_S3_ACCESS_KEY/TRACKER_S3_SECRET_KEY. Keep them secret;
MinIO remains on the internal network. The bucket must be private and dedicated to this DB.
Fresh buckets are private by default. Review existing bucket policies before adopting an
existing store; native startup does not remove policies set by an administrator.

```sh
docker compose up -d minio
# Healthcheck verifies both authentication and existence of the configured bucket:
docker compose ps minio
docker compose exec minio sh -c 'mc alias set check http://localhost:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null && mc ls "check/$MINIO_DEFAULT_BUCKETS"'
```

Repeating startup preserves bucket objects. Fresh installs with no legacy attachments can
run `docker compose up --build -d` directly. The backend automatically applies migrations.
`attachment-cleanup-worker` retries every 300 seconds. `attachment-scan-worker` automatically
checks pending files with ClamAV; monitor both workers for errors.

For a direct backend process configure TRACKER_S3_ENDPOINT (host:port, no scheme),
TRACKER_S3_BUCKET, TRACKER_S3_ACCESS_KEY, TRACKER_S3_SECRET_KEY, and TRACKER_S3_SECURE=true
for TLS. TLS certificates are verified. Compose uses internal HTTP. Missing credentials or
unavailable storage produces 503 for file operations; it never falls back to PostgreSQL bytes.

## Existing installations: explicit cutover

Use a maintenance window. Stop API writes and all workers before backup/transfer. Do not run
old and new API binaries together: the old version writes bytea without the storage lock.
Save a coordinated PostgreSQL backup and snapshot/copy of `minio_data` first. Build the new
backend image without starting it against the live schema.

```sh
docker compose stop backend deadline-worker registration-mail-worker attachment-cleanup-worker attachment-scan-worker
docker compose build backend
docker compose up -d db minio
docker compose run --rm --no-deps backend alembic upgrade 0015_attachment_objects
docker compose run --rm --no-deps backend python -m app.commands.attachments migrate
# Keep the pre-cutover backup until migration and restore verification are complete.
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up -d --build
```

`migrate` reads one file at a time in 1 MiB PostgreSQL substring chunks, validates it, writes a
new private object, reads it back and verifies size/SHA-256 before committing its reference.
IDs, associations, order, filenames (apart from safety normalization), comments and notification
records are preserved. Interruptions leave legacy bytes intact; rerun the same command.
Malformed legacy images are preserved as `failed` objects, unavailable through the API.
Size/checksum inconsistency stops the migration for operator investigation. Valid migrated
files are `pending` and enter automatic scanning just like new files. No unchecked bytes are released.

0016 refuses to drop legacy content while an attachment lacks a verified object reference.
No network I/O runs inside Alembic. After 0016, downgrade to 0015 recreates an empty nullable
content column; it does not reconstruct file bytes. Returning to old code requires the verified
pre-cutover DB backup or a separately verified reverse export, not just `alembic downgrade`.
Do not discard the backup until restore has been tested. During the maintenance window new
uploads are stopped; after cutover only the new version may publish files.

## Automatic quarantine checking

The default Compose stack starts `clamav` and `attachment-scan-worker`. The worker reads
pending objects from MinIO, verifies size/SHA-256 and file/image validity, then sends the same
bytes to ClamD using INSTREAM. Only an explicit clean verdict changes state to `ready`.
Detections (including encrypted archives and scan-limit alerts) become `infected`; integrity
or validation failures become `failed`. These states prohibit downloads. A rejected heuristic
verdict does not necessarily mean a confirmed virus.

Connection failures, scanner errors, timeouts and unavailable objects leave files `pending`
for retry. Existing pending files are also processed. Ready/rejected files are not rescanned.
The API remains available during scanner outages, but pending files remain inaccessible.
Chat refreshes pending attachment statuses automatically; no manual release is normally needed.

```sh
docker compose up -d --build
docker compose ps clamav attachment-scan-worker
docker compose logs --tail=100 clamav attachment-scan-worker
```

FreshClam updates signatures in `clamav_data` (24 checks/day); first startup waits for ClamD
readiness. Allow outbound access for signature updates and monitor update failures. ClamD's
unauthenticated port 3310 is internal only; do not publish it. ClamAV requires additional RAM
for its engine and signature database. Antivirus checks reduce risk but cannot guarantee safety.

`ATTACHMENT_SCAN_INTERVAL_SECONDS=5` controls delay between passes;
`ATTACHMENT_SCAN_TIMEOUT_SECONDS=60` bounds each ClamD request. Direct processes use
`TRACKER_` prefixes, plus `TRACKER_CLAMD_HOST` and `TRACKER_CLAMD_PORT`.
Run `python -m app.workers.attachment_scan` alongside a reachable ClamD when not using Compose.
Each worker scans one file at a time in a 64 MiB temporary filesystem, holding a PostgreSQL
row lock until the decision is committed. Other workers skip locked rows. A failed object
does not prevent checking subsequent objects. Archive limits are configured in Compose;
exceeding a limit is not treated as a clean scan.

## Manual quarantine review (operator fallback)

Operator commands require trusted database/storage credentials and are not HTTP endpoints.
Review is an explicit operational responsibility; a file-type check is not a malware scan.
Only release bytes that were scanned/reviewed according to the deployment's security policy.

```sh
python -m app.commands.attachments pending --limit 100
python -m app.commands.attachments export ATTACHMENT_UUID --output /tmp/review-file
# Scan the exported file using your organization's scanner in an isolated environment.
# Record its SHA-256 and choose one of the following decisions:
python -m app.commands.attachments review ATTACHMENT_UUID --sha256 SHA256 --state ready --reviewed-safe
python -m app.commands.attachments review ATTACHMENT_UUID --sha256 SHA256 --state infected
python -m app.commands.attachments review ATTACHMENT_UUID --sha256 SHA256 --state failed
```

Export creates an owner-readable/writable file exclusively, never overwriting a path. Release
re-downloads the object and verifies checksum, size and image safety before changing state.
Wrong IDs/checksums cannot accidentally release different bytes; rejected files cannot be
released. Review decisions are logged with ID, digest and state. Remove exported copies after
review. Pending/failed/infected attachments show a disabled download in chat; statuses refresh
automatically, with “Check file status” available for an immediate refresh. Access revocation and soft deletion still hide ready files.

## Cleanup and recovery

```sh
python -m app.commands.attachments cleanup
```

The worker runs the same idempotent operation. It aborts at most 100 abandoned multipart
uploads per pass, then deletes unreferenced objects in the dedicated attachment prefix.
A shared/exclusive PostgreSQL advisory lock prevents races with active publishers, including
uncommitted inserts. Cleanup retries after outages; it never deletes based on a failed DB read.
Attached pending/rejected files and files of soft-deleted resources are retained. There is no
user-facing deletion endpoint. Never run cleanup against a mismatched DB/bucket backup pair.
No MinIO lifecycle configuration is required or installed.

Back up PostgreSQL and MinIO together while writes and cleanup are stopped (or use coordinated
snapshots). Restore both from the same checkpoint, verify referenced objects, sizes and checksums,
then enable workers and API writes. Do not manually rename or overwrite objects. Missing objects
produce sanitized 503; restoring metadata alone cannot repair missing bytes. For old deployments
with a manually installed lifecycle rule, remove it through your existing administrative tooling
before adopting this configuration; the application does not modify bucket policies/lifecycles.

## Capacity

Default limits: 25 MiB/file, five files, 130 MiB/request, 40 million decoded pixels across frames.
Per backend process: two upload slots, four download slots; overflow is 429 with Retry-After.
TRACKER_ATTACHMENT_UPLOAD_SLOTS and TRACKER_ATTACHMENT_DOWNLOAD_SLOTS configure direct processes;
Compose exposes ATTACHMENT_UPLOAD_SLOTS/ATTACHMENT_DOWNLOAD_SLOTS. One backend worker is the
provided baseline. Plan aggregate limits explicitly before scaling workers/replicas.

TRACKER_S3_TIMEOUT_SECONDS defaults to 10 (connect 5). Request I/O uses
TRACKER_ATTACHMENT_IDLE_SECONDS=30 and TRACKER_ATTACHMENT_REQUEST_SECONDS=300.
The backend tmpfs is capped at 384 MiB, enough for two 130 MiB bodies; it counts as memory.
Image decoding and SDK buffers need additional bounded memory. For disk-backed spooling,
mount a capacity-limited writable /tmp. Disk exhaustion returns sanitized 503 and closes spools.
Both nginx layers disable request/response buffering. Keep equivalent settings in other proxies.


TASK-025: run runtime review/scanning only after upgrading through migration 0018. Legacy
`migrate` remains usable on the transitional 0015 schema before the final upgrade. Review and
scanner state transitions now append transactional security events; unchanged-state review
and failed/retried scans do not duplicate them. See ADR-013 for service-principal attribution.

The browser queues attachment downloads to avoid exhausting server download slots when a chat
contains many images. HTTP 429 is retried up to three times using Retry-After (1–30 seconds).
