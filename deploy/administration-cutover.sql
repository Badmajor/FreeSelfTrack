-- TASK-038: trusted maintenance role, head schema, API and all writers STOPPED.
-- Back up PostgreSQL + MinIO first. This intentionally signs out every old session.
-- Run with psql -v ON_ERROR_STOP=1; no credentials or session tokens are returned.
BEGIN;
SELECT pg_advisory_xact_lock(240031);
WITH operation AS (SELECT gen_random_uuid() AS request_id), revoked AS (
    UPDATE auth_sessions SET revoked_at = CURRENT_TIMESTAMP
    WHERE revoked_at IS NULL
    RETURNING id
)
INSERT INTO security_events
    (id, event_type, actor_kind, actor_id, target_type, target_id,
     organization_id, request_id, created_at, details)
SELECT gen_random_uuid(), 'session_revoked', 'bootstrap', NULL, 'session', id,
       NULL, operation.request_id, CURRENT_TIMESTAMP, '{}'::json
FROM revoked CROSS JOIN operation;
COMMIT;
