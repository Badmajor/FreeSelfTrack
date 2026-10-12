import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getEntityAudit, type AuditScope, type AdministrativeAuditEntry } from "./api";

const labels: Record<string, string> = {
  user_created: "User created", profile_updated: "Profile updated",
  user_blocked: "User blocked", user_unblocked: "User unblocked",
  system_role_changed: "System role changed", created: "Created", updated: "Updated",
  workflow_changed: "Workflow changed", member_added: "Member added",
  member_removed: "Member removed", member_role_changed: "Member role changed",
  archived: "Archived", restored: "Restored",
};

function valueText(value: AdministrativeAuditEntry["changes"][number]["old"]): string {
  if (value === null) return "None";
  if (Array.isArray(value)) return value.map(status =>
    `${status.name} (${status.id}), position ${status.position}, ${status.is_active ? "active" : "inactive"}, ${status.is_completed ? "completed" : "not completed"}`,
  ).join("; ") || "None";
  return String(value);
}

export function EntityAudit({ scope, id }: { scope: AuditScope; id: string }) {
  return <AuditPages key={`${scope}-${id}`} scope={scope} id={id} />;
}

function AuditPages({ scope, id }: { scope: AuditScope; id: string }) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [page, setPage] = useState(0);
  const audit = useQuery({
    queryKey: ["entity-audit", scope, id, cursors[page]],
    queryFn: () => getEntityAudit(scope, id, cursors[page]),
    staleTime: 0,
  });
  return (
    <section aria-label="Administrative audit" className="entity-audit">
      <h3>Administrative audit</h3>
      <button type="button" disabled={audit.isFetching} onClick={() => {
        setCursors([undefined]); setPage(0);
        if (page === 0) void audit.refetch();
      }}>Refresh audit</button>
      {audit.isFetching && <p role="status">Loading audit...</p>}
      {audit.isError && <p role="alert">{audit.error.message}{" "}
        <button type="button" onClick={() => void audit.refetch()}>Retry audit</button>
      </p>}
      {audit.isSuccess && !audit.isFetching && <>
        {audit.data.items.length === 0 && <p>No audit entries.</p>}
        <ol>
          {audit.data.items.map(entry => <li key={entry.id}>
            <p><strong>{entry.actor.display_name}</strong>{" · "}
              <time dateTime={entry.occurred_at}>{new Date(entry.occurred_at).toLocaleString()}</time>
              {" · "}{labels[entry.action] ?? entry.action}
            </p>
            {entry.subject_user_id && <p>Member: {entry.subject_user_id}</p>}
            <dl>{entry.changes.map(change => <div key={change.field}>
              <dt>{change.field.replaceAll("_", " ")}</dt>
              <dd>Old: {valueText(change.old)} → New: {valueText(change.new)}</dd>
            </div>)}</dl>
            <details><summary>Operation</summary>{entry.operation_id}</details>
          </li>)}
        </ol>
      </>}
      <nav aria-label="Audit pagination">
        <button type="button" disabled={page === 0 || audit.isFetching} onClick={() => setPage(page - 1)}>Previous audit page</button>
        <span aria-live="polite"> Page {page + 1} </span>
        <button type="button" disabled={!audit.isSuccess || !audit.data.next_cursor || audit.isFetching} onClick={() => {
          const next = audit.data?.next_cursor;
          if (next) { setCursors([...cursors.slice(0, page + 1), next]); setPage(page + 1); }
        }}>Next audit page</button>
      </nav>
    </section>
  );
}
