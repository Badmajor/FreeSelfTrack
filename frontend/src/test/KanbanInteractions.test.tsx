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
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
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
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) return response(board);
      if (url === "/api/tasks/task-1" && options?.method === "PATCH") return response({ detail: "You cannot change this task" }, 403);
      if (url.includes("/tasks/task-1/history")) return response({ entries: [], next_cursor: null });
      if (url.includes("/tasks/task-1/watchers")) return response([]);
      if (url.includes("/projects/project-1/members")) return response([]);
      if (url === "/api/tasks/task-1") return response(task);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView({ id: "member-1", email: "member@example.com" });
    await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));
    const statusMenu = await screen.findByLabelText("Status");
    await userEvent.selectOptions(statusMenu, "status-done");

    expect(await screen.findByRole("alert")).toHaveTextContent("You cannot change this task");
    await waitFor(() => expect(statusMenu).toHaveValue("status-backlog"));
  });

  it("persists column width locally and disables restricted participant controls", async () => {
    const assignedTask = { ...task, assignee_id: "owner-1" };
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
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
  it("allows the project owner to create a column and refreshes the board", async () => {
    const createdStatus = { id: "status-review", project_id: project.id, name: "Review", position: 2, is_active: true };
    const updatedBoard = { ...board, columns: [...board.columns, { status: createdStatus, tasks: [], next_cursor: null }] };
    let boardRequests = 0;
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) {
        boardRequests += 1;
        return response(boardRequests === 1 ? board : updatedBoard);
      }
      if (url === "/api/projects/project-1/statuses" && options?.method === "POST") return response(createdStatus, 201);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView();

    await userEvent.click(await screen.findByRole("button", { name: "Add column" }));
    await userEvent.type(screen.getByLabelText("Column name"), "  Review  ");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/statuses",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Review" }) }),
    ));
    expect(await screen.findByRole("heading", { name: "Review" })).toBeInTheDocument();
    expect(screen.queryByRole("form", { name: "Add column form" })).not.toBeInTheDocument();
  });

  it("keeps the column name when creation fails and prevents blank submissions", async () => {
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) return response(board);
      if (url === "/api/projects/project-1/statuses" && options?.method === "POST") return response({ detail: "Only the project owner can manage statuses" }, 403);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView();

    await userEvent.click(await screen.findByRole("button", { name: "Add column" }));
    const input = screen.getByLabelText("Column name");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Column name is required");
    expect(fetchMock).not.toHaveBeenCalledWith("/api/projects/project-1/statuses", expect.anything());

    await userEvent.type(input, "Review");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Only the project owner can manage statuses");
    expect(screen.getByLabelText("Column name")).toHaveValue("Review");
  });

  it("does not expose column creation to project members", async () => {
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(response(board)));
    renderView({ id: "member-1", email: "member.com" });

    await screen.findByRole("heading", { name: "Backlog" });
    expect(screen.queryByRole("button", { name: "Add column" })).not.toBeInTheDocument();
  });
  it("reorders columns for the project owner", async () => {
    const reorderedBoard = { ...board, columns: [board.columns[1], board.columns[0]] };
    let boardRequests = 0;
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) {
        boardRequests += 1;
        return response(boardRequests === 1 ? board : reorderedBoard);
      }
      if (url === "/api/projects/project-1/statuses/reorder" && options?.method === "POST") return response([reorderedBoard.columns[0].status, reorderedBoard.columns[1].status]);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView();
    await screen.findByRole("heading", { name: "Backlog" });

    const backlogHeader = screen.getByRole("heading", { name: "Backlog" }).parentElement?.parentElement as HTMLElement;
    fireEvent.dragStart(backlogHeader);
    expect(screen.getByLabelText("Reorder Backlog column")).toBe(backlogHeader);
    fireEvent.drop(screen.getByRole("heading", { name: "Done" }).closest(".kanban-column") as HTMLElement);

    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/statuses/reorder",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ status_ids: ["status-done", "status-backlog"] }) }),
    ));
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Done", "Backlog"]));
  });

  it("rolls back column order when reorder fails and hides controls for members", async () => {
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) return response(board);
      if (url.includes("/statuses/reorder") && options?.method === "POST") return response({ detail: "Only the project owner can manage statuses" }, 403);
      return response([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderView();
    await screen.findByRole("heading", { name: "Backlog" });
    const backlogHeader = screen.getByRole("heading", { name: "Backlog" }).parentElement?.parentElement as HTMLElement;
    fireEvent.dragStart(backlogHeader);
    expect(screen.getByLabelText("Reorder Backlog column")).toBe(backlogHeader);
    fireEvent.drop(screen.getByRole("heading", { name: "Done" }).closest(".kanban-column") as HTMLElement);

    expect(await screen.findByRole("alert")).toHaveTextContent("Only the project owner can manage statuses");
    await waitFor(() => expect(screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent)).toEqual(["Backlog", "Done"]));

    cleanup();
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(response(board)));
    renderView({ id: "member-1", email: "member.com" });
    await screen.findByRole("heading", { name: "Backlog" });
    const memberHeader = screen.getByRole("heading", { name: "Backlog" }).parentElement?.parentElement as HTMLElement;
    expect(memberHeader).not.toHaveAttribute("draggable", "true");
  });
});
