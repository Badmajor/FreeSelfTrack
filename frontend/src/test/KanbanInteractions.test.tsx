import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import type { Project } from "../api";

const project: Project = {
  id: "project-1",
  organization_id: "organization-1",
  owner_id: "owner-1",
  name: "Product",
};

const task = {
  id: "task-1",
  project_id: project.id,
  status_id: "status-backlog",
  title: "First task",
  description: null,
  created_by: "owner-1",
  reporter_id: "owner-1",
  assignee_id: null,
  watchers: [],
  created_at: "2026-01-01T10:00:00Z",
  updated_at: "2026-01-02T10:00:00Z",
};

const board = {
  project_id: project.id,
  columns: [
    {
      status: { id: "status-backlog", project_id: project.id, name: "Backlog", position: 0, is_active: true },
      tasks: [task],
      next_cursor: "cursor-backlog",
    },
    {
      status: { id: "status-done", project_id: project.id, name: "Done", position: 1, is_active: true },
      tasks: [],
      next_cursor: "cursor-done",
    },
  ],
};

function renderView(currentUser = { id: "owner-1", email: "owner@example.com" }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <KanbanView project={project} currentUser={currentUser} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

function response(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("Kanban interactions", () => {
  it("loads the next page independently for each column", async () => {
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/board?")) return response(board);
      if (url.includes("status-backlog/tasks")) return response({ tasks: [{ ...task, id: "task-2", title: "Loaded later" }], next_cursor: null });
      if (url.includes("status-done/tasks")) return response({ tasks: [{ ...task, id: "task-3", status_id: "status-done", title: "Done later" }], next_cursor: null });
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView();
    await screen.findByText("First task");

    const backlogList = screen.getByRole("heading", { name: "Backlog" }).parentElement?.parentElement?.parentElement?.querySelector(".task-list") as HTMLElement;
    Object.defineProperties(backlogList, { scrollTop: { value: 100 }, clientHeight: { value: 100 }, scrollHeight: { value: 100 } });
    fireEvent.scroll(backlogList);
    await screen.findByText("Loaded later");
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/board/columns/status-backlog/tasks?limit=500&cursor=cursor-backlog", expect.anything());

    const doneList = screen.getByRole("heading", { name: "Done" }).parentElement?.parentElement?.parentElement?.querySelector(".task-list") as HTMLElement;
    Object.defineProperties(doneList, { scrollTop: { value: 100 }, clientHeight: { value: 100 }, scrollHeight: { value: 100 } });
    fireEvent.scroll(doneList);
    await screen.findByText("Done later");
    expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1/board/columns/status-done/tasks?limit=500&cursor=cursor-done", expect.anything());
  });

  it("shows a mutation error and rolls the card back", async () => {
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/board?")) return response(board);
      if (url === "/api/tasks/task-1" && options?.method === "PATCH") return response({ detail: "You cannot change this task" }, 403);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView({ id: "member-1", email: "member@example.com" });
    const statusMenu = await screen.findByRole("combobox", { name: "Status for task-1" });
    await userEvent.selectOptions(statusMenu, "status-done");

    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot change this task");
    await waitFor(() => expect(statusMenu).toHaveValue("status-backlog"));
  });

  it("persists column width locally and disables restricted participant controls", async () => {
    const assignedTask = { ...task, assignee_id: "owner-1" };
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/board?")) return response({ ...board, columns: [{ ...board.columns[0], tasks: [assignedTask] }, board.columns[1]] });
      if (url.includes("/tasks/task-1/history")) return response({ entries: [], next_cursor: null });
      if (url.includes("/tasks/task-1/watchers")) return response([]);
      if (url.includes("/tasks/task-1")) return response(assignedTask);
      if (url.includes("/projects/project-1/members")) return response([{ id: "owner-1", email: "owner@example.com" }, { id: "member-1", email: "member@example.com" }]);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView({ id: "member-1", email: "member@example.com" });
    const width = await screen.findByRole("separator", { name: "Resize Backlog column" });
    fireEvent.keyDown(width, { key: "ArrowRight" });
    expect(JSON.parse(window.localStorage.getItem("freeselftrack.kanban.widths.project-1") ?? "{}")).toMatchObject({ "status-backlog": 300 });

    await userEvent.click(screen.getByRole("article", { name: "Open task task-1" }));
    expect(await screen.findByLabelText("Assignee")).toBeDisabled();
    expect(screen.getByLabelText("Reporter")).toBeDisabled();
  });
});
