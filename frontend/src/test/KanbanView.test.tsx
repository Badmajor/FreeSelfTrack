import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import type { Project } from "../api";

const project: Project = {
  id: "project-1",
  organization_id: "organization-1",
  owner_id: "user-1",
  name: "Product",
};

const board = {
  project_id: project.id,
  columns: [
    {
      status: { id: "status-backlog", project_id: project.id, name: "Backlog", position: 0, is_active: true },
      tasks: [{
        id: "task-1",
        project_id: project.id,
        status_id: "status-backlog",
        title: "First task",
        description: null,
        created_by: "user-1",
        reporter_id: "user-1",
        assignee_id: null,
        watchers: [],
        created_at: "2026-01-01T10:00:00Z",
        updated_at: "2026-01-02T10:00:00Z",
      }],
      next_cursor: null,
    },
    {
      status: { id: "status-done", project_id: project.id, name: "Done", position: 1, is_active: true },
      tasks: [],
      next_cursor: null,
    },
  ],
};

function renderView() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <KanbanView project={project} currentUser={{ id: "user-1", email: "owner@example.com" }} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("KanbanView", () => {
  it("renders backend-provided columns and task summaries", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify(board), { status: 200 })));

    renderView();

    expect(await screen.findByText("Backlog")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Done" })).toBeInTheDocument();
    expect(screen.getByText("First task")).toBeInTheDocument();
    expect(screen.getByText("task-1")).toBeInTheDocument();
    expect(screen.getByText("Unassigned")).toBeInTheDocument();
  });

  it("updates a task status through the card menu", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(board), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ ...board.columns[0].tasks[0], status_id: "status-done" }), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderView();
    const statusMenu = await screen.findByRole("combobox", { name: "Status for task-1" });
    await userEvent.selectOptions(statusMenu, "status-done");

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status_id: "status-done" }) }),
    ));
  });
});
