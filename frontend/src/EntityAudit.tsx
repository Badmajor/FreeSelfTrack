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

type Props = { scope: AuditScope; id: string; presentation?: "organization" | "project" };

export function EntityAudit({ scope, id, presentation }: Props) {
  return <AuditPages key={`${scope}-${id}`} scope={scope} id={id} presentation={presentation} />;
}

function AuditPages({ scope, id, presentation }: Props) {
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const [page, setPage] = useState(0);
  const audit = useQuery({
    queryKey: ["entity-audit", scope, id, cursors[page]],
    queryFn: () => getEntityAudit(scope, id, cursors[page]),
    staleTime: 0,
  });
  return (
    <section aria-label="Administrative audit" className="entity-audit">
      {!presentation && <h3>Administrative audit</h3>}
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
            <p>{presentation && <strong>{labels[entry.action] ?? (presentation === "project" ? entry.action.replaceAll("_", " ") : entry.action)}<br /></strong>}<span className={presentation ? "audit-meta" : undefined}><strong>{entry.actor.display_name}</strong>{" · "}
              <time dateTime={entry.occurred_at}>{new Date(entry.occurred_at).toLocaleString()}</time>
              {!presentation && <>{" · "}{labels[entry.action] ?? entry.action}</>}</span>
            </p>
            {presentation === "project" ? <details><summary>Details</summary><AuditDetails entry={entry} presentation={presentation} /></details> : <AuditDetails entry={entry} presentation={presentation} />}

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

function AuditDetails({ entry, presentation }: { entry: AdministrativeAuditEntry; presentation?: Props["presentation"] }) {
  return <>
    {entry.subject_user_id && <p>Member: {entry.subject_user_id}</p>}
    <dl>{entry.changes.map(change => <div key={change.field}>
      <dt>{change.field.replaceAll("_", " ")}</dt>
      <dd>{presentation ? <div className={presentation === "project" ? "project-audit-values" : "organization-audit-values"}><div><span>Old</span>{valueText(change.old)}</div><div><span>New</span>{valueText(change.new)}</div></div> : <>Old: {valueText(change.old)} → New: {valueText(change.new)}</>}</dd>
    </div>)}</dl>
    {presentation === "project" ? <dl><dt>Operation</dt><dd>{entry.operation_id}</dd></dl> : <details><summary>Operation</summary>{entry.operation_id}</details>}
  </>;
}
