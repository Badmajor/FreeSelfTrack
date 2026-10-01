import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Link2, Trash2 } from "lucide-react";

import {
  createTaskLink,
  deleteTaskLink,
  listTaskLinks,
  searchOrganizationTasks,
  type TaskLinkRelation,
} from "./api";

export type LinkSelection = {
  sourceTaskId: string;
  sourceProjectId: string;
  sourceSlug: string;
  organizationId: string;
  relationType: TaskLinkRelation;
};

type Props = {
  taskId: string;
  taskSlug: string;
  projectId: string;
  organizationId: string;
  canManage: boolean;
  onOpenTask: (projectId: string, taskId: string) => void;
  onStartSelection: (selection: LinkSelection) => void;
};

const labels: Record<TaskLinkRelation, string> = {
  blocks: "Blocks",
  depends_on: "Depends on",
  related: "Related",
};

export function TaskLinks({
  taskId,
  taskSlug,
  projectId,
  organizationId,
  canManage,
  onOpenTask,
  onStartSelection,
}: Props) {
  const client = useQueryClient();
  const [relationType, setRelationType] =
    useState<TaskLinkRelation>("related");
  const [slug, setSlug] = useState("");
  const query = slug.trim();
  const [debouncedQuery, setDebouncedQuery] = useState("");
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query), 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  const searchReady = canManage && query.length > 2 && query === debouncedQuery;
  const links = useQuery({
    queryKey: ["task-links", taskId],
    queryFn: () => listTaskLinks(taskId),
  });
  const search = useQuery({
    queryKey: ["task-link-search", organizationId, debouncedQuery],
    queryFn: () => searchOrganizationTasks(organizationId, debouncedQuery),
    enabled: searchReady,
  });
  const results = searchReady
    ? (search.data?.items.filter((item) => item.id !== taskId) ?? [])
    : [];
  const create = useMutation({
    mutationFn: (targetTaskId: string) =>
      createTaskLink(taskId, targetTaskId, relationType),
    onSuccess: async () => {
      setSlug("");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["task-links", taskId] }),
        client.invalidateQueries({ queryKey: ["task-history", taskId] }),
      ]);
    },
  });
  const remove = useMutation({
    mutationFn: (linkId: string) => deleteTaskLink(taskId, linkId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["task-links", taskId] }),
        client.invalidateQueries({ queryKey: ["task-history", taskId] }),
      ]);
    },
  });

  return (
    <section className="task-links" aria-label="Task links">
      {canManage && (
        <div className="task-link-controls">
          <div className="task-link-row">
            <div className="task-link-field">
              <label htmlFor="task-link-type">Relationship</label>
              <select
                id="task-link-type"
                value={relationType}
                onChange={(event) =>
                  setRelationType(event.target.value as TaskLinkRelation)
                }
              >
                <option value="blocks">Blocks</option>
                <option value="depends_on">Depends on</option>
                <option value="related">Related</option>
              </select>
            </div>
            <div className="task-link-field">
              <label htmlFor="task-link-slug">Task number</label>
              <input
                id="task-link-slug"
                value={slug}
                placeholder="TRA-123"
                aria-describedby="task-link-search-hint"
                onChange={(event) => setSlug(event.target.value)}
              />
            </div>
            <button
              className="icon-button select-task-link"
              aria-label="Select on board"
              title="Select on board"
              type="button"
              onClick={() =>
                onStartSelection({
                  sourceTaskId: taskId,
                  sourceProjectId: projectId,
                  sourceSlug: taskSlug,
                  organizationId,
                  relationType,
                })
              }
            >
              <Link2 aria-hidden="true" />
            </button>
          </div>
          <p id="task-link-search-hint" className="muted">Enter at least 3 characters to search.</p>
          {query.length > 2 && (!searchReady || search.isFetching) && (
            <p role="status">Searching...</p>
          )}
          {searchReady && search.isError && (
            <p className="error" role="alert">
              {message(search.error)}
            </p>
          )}
          {searchReady && search.isSuccess && !search.isFetching && !results.length && (
            <p className="muted">No matching tasks.</p>
          )}
          {!!results.length && (
            <ul className="task-link-results" aria-label="Matching tasks">
              {results.map((task) => (
                <li key={task.id}>
                  <button
                    type="button"
                    disabled={create.isPending}
                    onClick={() => create.mutate(task.id)}
                  >
                    <strong>{task.slug}</strong>
                    <span>{task.title}</span>
                    <small>
                      {task.project_name} · {task.status_name}
                    </small>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
      {create.isError && (
        <p className="error" role="alert">
          {message(create.error)}
        </p>
      )}
      {remove.isError && (
        <p className="error" role="alert">
          {message(remove.error)}
        </p>
      )}
      {links.isPending && <p role="status">Loading links...</p>}
      {links.isError && (
        <div>
          <p className="error" role="alert">
            Unable to load links.
          </p>
          <button type="button" onClick={() => void links.refetch()}>
            Retry links
          </button>
        </div>
      )}
      {links.data && !links.data.length && (
        <p className="muted">No linked tasks.</p>
      )}
      {!!links.data?.length && (
        <ul className="task-links-list">
          {links.data.map((link) => (
            <li key={link.id}>
              <span className="task-link-kind">
                {labels[link.relation_type]}
              </span>
              <button
                className="task-link-target"
                type="button"
                onClick={() =>
                  onOpenTask(link.task.project_id, link.task.id)
                }
              >
                <strong>{link.task.slug}</strong>
                <span>{link.task.title}</span>
                <small>
                  {link.task.project_name} · {link.task.status_name}
                </small>
                <ExternalLink aria-hidden="true" />
              </button>
              {canManage && (
                <button
                  className="icon-button danger-icon"
                  type="button"
                  disabled={remove.isPending}
                  aria-label={`Remove link to ${link.task.slug}`}
                  title="Remove link"
                  onClick={() => remove.mutate(link.id)}
                >
                  <Trash2 aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function message(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}
