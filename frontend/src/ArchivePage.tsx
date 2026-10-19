import { useEffect, useRef, useState } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { Archive, Info, RotateCcw } from "lucide-react";
import { ApiError, archivePage, restoreResource, type ArchiveResource } from "./api";

type Scope = "organization" | "project" | "task";
const consequences: Record<Scope, string> = {
  organization: "The organization will become active. Projects and tasks will stay archived. Previous memberships of the organization and all its projects will be revoked. Participants must be added again.",
  project: "The project will become active. Tasks will stay archived. Previous project memberships will be revoked. Participants must be added again.",
  task: "Only this task will become active. Its project and workflow will not change.",
};
function errorMessage(error: Error) {
  if (error instanceof ApiError) {
    if (error.status === 403) return "You no longer have permission to perform this operation.";
    if (error.status === 404) return "This resource is no longer available.";
    if (error.status === 409) return "Unable to restore this resource. Restore its parent organization or project first, then retry.";
  }
  return error.message;
}

export function ArchivePage() {
  const [params] = useSearchParams();
  const scope = params.get("project") ? "task" : params.get("organization") ? "project" : "organization";
  const parent = params.get("project") ?? params.get("organization") ?? undefined;
  return <ArchiveContext key={`${scope}:${parent ?? ""}`} scope={scope} parent={parent} />;
}

function ArchiveContext({ scope, parent }: { scope: Scope; parent?: string }) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<ArchiveResource | null>(null);
  const [success, setSuccess] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  const mounted = useRef(true);
  const submitting = useRef(false);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const resources = useInfiniteQuery({
    queryKey: ["archive", scope, parent],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => archivePage(scope, parent, pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const restore = useMutation({
    mutationFn: (item: ArchiveResource) => restoreResource(scope, item.id),
    onSuccess: async (_, item) => {
      await client.invalidateQueries();
      if (!mounted.current) return;
      setSelected(null);
      setSuccess(`“${item.name ?? item.title}” restored.`);
      requestAnimationFrame(() => { if (mounted.current) heading.current?.focus(); });
    },
    onSettled: () => { submitting.current = false; },
  });
  const items = resources.data?.pages.flatMap(page => page.items) ?? [];
  const title = `Archived ${scope}s`;
  return <section className="route-page archive-page">
    <header className="archive-header">
      <div><h1 ref={heading} tabIndex={-1}>{title}</h1><p>Browse archived {scope}s and restore them when needed.</p></div>
      <Link className="button secondary" to={scope === "organization" ? "/management/organizations" : "/archive"}>
        {scope === "organization" ? "Active organizations" : "Archived organizations"}
      </Link>
    </header>
    <aside className="archive-info" aria-label="Restoration rules"><Info size={20} aria-hidden="true" /><div>
      <strong>Restoring from the archive</strong>
      <p>Restore parents first: organization, then project, then task. Children stay archived.</p>
      <p>Restoring organizations or projects revokes previous memberships. Add participants again.</p>
    </div></aside>
    <p role="status" className="archive-feedback">{success}</p>
    {resources.isPending && <p className="archive-state" role="status">Loading archive…</p>}
    {resources.isError && !resources.isFetchNextPageError && <div className="archive-state" role="alert">
      <p>{errorMessage(resources.error)}</p><button className="button secondary" disabled={resources.isFetching} onClick={() => void resources.refetch()}>Retry</button>
    </div>}
    {resources.data && <>
      {items.length ? <ul className="archive-list" aria-label={title}>{items.map(item => <li key={item.id}>
        <Link className="archive-name" to={scope === "task" ? `/projects/${parent}/kanban/tasks/${item.id}` : `/management/${scope}s/${item.id}`}>{item.name ?? item.title}</Link>
        <div className="archive-actions">
          {scope !== "task" && <Link className="button secondary" aria-label={`Archived ${scope === "organization" ? "projects" : "tasks"} of ${item.name}`} to={`/archive?${scope}=${encodeURIComponent(item.id)}`}>Archived {scope === "organization" ? "projects" : "tasks"}</Link>}
          {item.capabilities?.restore && <button className="button" aria-label={`Restore ${item.name ?? item.title}`} onClick={() => { restore.reset(); setSelected(item); }}><RotateCcw size={16} aria-hidden="true" />Restore</button>}
        </div>
      </li>)}</ul> : <div className="archive-state"><Archive aria-hidden="true" /><h2>No archived {scope}s</h2>{scope === "organization" && <Link className="button secondary" to="/management/organizations">Active organizations</Link>}</div>}
      {resources.isFetchNextPageError && <p role="alert">Could not load more {scope}s. {errorMessage(resources.error)}</p>}
      {resources.hasNextPage && <button className="button secondary archive-more" disabled={resources.isFetchingNextPage} onClick={() => void resources.fetchNextPage()}>{resources.isFetchingNextPage ? "Loading more…" : resources.isFetchNextPageError ? "Retry loading more" : "Load more"}</button>}
      {resources.isFetchingNextPage && <p role="status">Loading more {scope}s…</p>}
    </>}
    {selected && <RestoreDialog scope={scope} item={selected} pending={restore.isPending} error={restore.error} onCancel={() => { if (!submitting.current) setSelected(null); }} onRestore={() => {
      if (submitting.current) return;
      submitting.current = true;
      restore.mutate(selected);
    }} />}
  </section>;
}

function RestoreDialog({ scope, item, pending, error, onCancel, onRestore }: {
  scope: Scope; item: ArchiveResource; pending: boolean; error: Error | null; onCancel: () => void; onRestore: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const cancel = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal(); else dialog?.setAttribute("open", "");
    cancel.current?.focus();
    return () => { dialog?.close?.(); if (previous instanceof HTMLElement && previous.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} aria-labelledby="restore-title" aria-describedby="restore-description" onCancel={event => { event.preventDefault(); onCancel(); }} onKeyDown={event => {
    if (event.key === "Escape") { event.preventDefault(); onCancel(); }
    if (event.key === "Tab") {
      const buttons = Array.from(ref.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? []);
      const next = event.shiftKey ? buttons.at(-1) : buttons[0];
      if (document.activeElement === (event.shiftKey ? buttons[0] : buttons.at(-1))) { event.preventDefault(); next?.focus(); }
    }
  }}>
    <h2 id="restore-title">Restore {scope}?</h2>
    <div id="restore-description"><p><strong>“{item.name ?? item.title}”</strong></p><p>{consequences[scope]}</p></div>
    {error && <p role="alert">{errorMessage(error)}</p>}
    {pending && <p role="status">Restoring…</p>}
    <div className="archive-actions"><button ref={cancel} className="button secondary" aria-disabled={pending} onClick={onCancel}>Cancel</button><button className="button" disabled={pending} onClick={onRestore}>{pending ? "Restoring…" : `Restore ${scope}`}</button></div>
  </dialog>;
}
