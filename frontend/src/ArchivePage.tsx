import { useState } from "react";
import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import { archivePage, restoreResource, type ArchiveResource } from "./api";

export function ArchivePage() {
  const [params, setParams] = useSearchParams();
  const scope = params.get("project")
    ? "task"
    : params.get("organization") ? "project" : "organization";
  const parent = params.get("project") ?? params.get("organization") ?? undefined;
  const [error, setError] = useState("");
  const client = useQueryClient();
  const resources = useInfiniteQuery({
    queryKey: ["archive", scope, parent],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => archivePage(scope, parent, pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const restore = useMutation({
    mutationFn: (item: ArchiveResource) => restoreResource(scope, item.id),
    onSuccess: async () => {
      setError("");
      await client.invalidateQueries();
    },
    onError: (err: Error) => setError(err.message),
  });

  return (
    <section className="page">
      <h1>Archive</h1>
      <p>
        Restore the organization first, then projects and tasks. Children stay archived.
        Organization and project restoration revokes previous memberships; add participants again.
      </p>
      <button onClick={() => setParams({})}>Organizations</button>
      <Link to="/management/organizations">Active organizations</Link>
      {resources.isPending && <p>Loading archive...</p>}
      {resources.isError && (
        <p role="alert">
          {resources.error.message}
          <button onClick={() => void resources.refetch()}>Retry</button>
        </p>
      )}
      {error && <p role="alert">{error}</p>}
      {resources.data?.pages.flatMap(page => page.items).map(item => (
        <article key={item.id} className="management-item">
          <Link to={scope === "task"
            ? `/projects/${parent}/kanban/tasks/${item.id}`
            : `/management/${scope}s/${item.id}`}>
            {item.name ?? item.title}
          </Link>
          {scope !== "task" && (
            <button onClick={() => setParams({ [scope]: item.id })}>
              Archived {scope === "organization" ? "projects" : "tasks"}
            </button>
          )}
          {item.capabilities?.restore && (
            <button
              disabled={restore.isPending}
              onClick={() => {
                const message = scope === "task"
                  ? "Restore this task?"
                  : "Restore this object? Previous memberships will be revoked. Children remain archived.";
                if (window.confirm(message)) restore.mutate(item);
              }}
            >
              Restore
            </button>
          )}
        </article>
      ))}
      {resources.data && !resources.data.pages[0].items.length && <p>No archived objects.</p>}
      {resources.hasNextPage && (
        <button
          disabled={resources.isFetchingNextPage}
          onClick={() => void resources.fetchNextPage()}
        >
          Load more
        </button>
      )}
    </section>
  );
}
