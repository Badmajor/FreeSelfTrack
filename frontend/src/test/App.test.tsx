import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestQueryClient, jsonResponse, makeBoard, makeTask, testProject } from "./test-utils";

const user = { id: "owner-1", email: "owner@example.com", is_active: true };
const organization = { id: "organization-1", owner_id: "owner-1", name: "Acme" };

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("App workspace", () => {
  it("opens Kanban from the selected project", async () => {
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/organizations")) return jsonResponse([organization]);
      if (url.endsWith("/organizations/organization-1/projects")) return jsonResponse([testProject]);
      if (url.endsWith("/projects/project-1/members")) return jsonResponse([user]);
      if (url.includes("/notifications/unread-count")) return jsonResponse({ count: 0 });
      if (url.includes("/projects/project-1/board?")) return jsonResponse(makeBoard());
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    window.localStorage.setItem("freeselftrack.access_token", "token");
    window.localStorage.setItem("freeselftrack.user", JSON.stringify(user));
    const { App } = await import("../App");

    render(<QueryClientProvider client={createTestQueryClient()}><App /></QueryClientProvider>);

    await screen.findByRole("heading", { name: "Product" });
    expect(screen.getByLabelText("Organization")).toHaveValue("organization-1");
    expect(screen.getByLabelText("Project")).toHaveValue("project-1");

    expect(screen.queryByRole("button", { name: "Add member" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Members" }));
    expect(await screen.findByRole("heading", { name: "Members" })).toBeInTheDocument();
    expect(screen.getByLabelText("Project")).toHaveValue("project-1");
    await userEvent.click(screen.getByRole("button", { name: "Back to workspace" }));
    expect(screen.getByLabelText("Organization")).toHaveValue("organization-1");
    expect(screen.getByLabelText("Project")).toHaveValue("project-1");
    await userEvent.click(screen.getByRole("button", { name: "Open Kanban" }));
    expect(await screen.findByRole("region", { name: "Product Kanban" })).toBeInTheDocument();
    expect(screen.getByText("First task")).toBeInTheDocument();
  });
});

describe("Kanban task workflow", () => {
  it("creates a task inside the selected column", async () => {
    const task = makeTask({ id: "task-new", title: "Created task" });
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/board?")) return jsonResponse(makeBoard());
      if (url === "/api/projects/project-1/tasks" && options?.method === "POST") return jsonResponse(task);
      return jsonResponse(makeBoard());
    });
    vi.stubGlobal("fetch", fetchMock);
    const { KanbanView } = await import("../KanbanView");

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView project={testProject} currentUser={user} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    await screen.findByText("First task");
    await userEvent.click(within(screen.getByRole("region", { name: "Backlog" })).getByRole("button", { name: "Add task" }));
    await userEvent.type(screen.getByLabelText("Title"), "Created task");
    await userEvent.click(screen.getByRole("button", { name: "Create" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects/project-1/tasks",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ title: "Created task", description: null, status_id: "status-backlog" }) }),
    ));
  });

  it("edits task details and closes the task drawer", async () => {
    const task = makeTask();
    const saved = { ...task, title: "Updated task", description: "Details" };
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/board?")) return jsonResponse(makeBoard(task));
      if (url === "/api/tasks/task-1" && options?.method === "PATCH") return jsonResponse(saved);
      if (url.includes("/tasks/task-1/history")) return jsonResponse({ entries: [], next_cursor: null });
      if (url.includes("/tasks/task-1/watchers")) return jsonResponse([]);
      if (url.includes("/tasks/task-1")) return jsonResponse(task);
      if (url.includes("/projects/project-1/members")) return jsonResponse([user]);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { KanbanView } = await import("../KanbanView");

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView project={testProject} currentUser={user} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));
    const title = await screen.findByLabelText("Title");
    await userEvent.clear(title);
    await userEvent.type(title, "Updated task");
    await userEvent.clear(screen.getByLabelText("Description"));
    await userEvent.type(screen.getByLabelText("Description"), "Details");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ title: "Updated task", description: "Details" }) }),
    ));
    await userEvent.click(screen.getByRole("button", { name: "Close task details" }));
    expect(screen.queryByRole("dialog", { name: "Task details" })).not.toBeInTheDocument();
  });

  it("moves a task through drag-and-drop to another column", async () => {
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/board?")) return jsonResponse(makeBoard());
      if (url === "/api/tasks/task-1" && options?.method === "PATCH") return jsonResponse(makeTask({ status_id: "status-done" }));
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    const { KanbanView } = await import("../KanbanView");
    const { fireEvent } = await import("@testing-library/react");

    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView project={testProject} currentUser={user} onClose={vi.fn()} />
      </QueryClientProvider>,
    );

    const card = await screen.findByRole("article", { name: "Open task task-1" });
    fireEvent.dragStart(card);
    fireEvent.drop(screen.getByRole("region", { name: "Done" }));

    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1",
      expect.objectContaining({ method: "PATCH", body: JSON.stringify({ status_id: "status-done" }) }),
    ));
  });
});
