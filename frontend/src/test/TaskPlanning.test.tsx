import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import type { Board, Task } from "../api";
import {
  createTestQueryClient,
  jsonResponse,
  makeBoard,
  makeTask,
  testProject,
} from "./test-utils";

function renderView(
  board: Board,
  currentUser = { id: "owner-1", email: "owner@example.com" },
) {
  vi.stubGlobal("fetch", createFetch(board));
  return render(
    <QueryClientProvider client={createTestQueryClient()}>
      <KanbanView
        project={{ ...testProject, capabilities: { ...testProject.capabilities, edit: currentUser.id === "owner-1" } }}
        currentUser={currentUser}
        onClose={vi.fn()}
      />
    </QueryClientProvider>,
  );
}

function createFetch(
  board: Board,
  patch?: (options?: RequestInit) => Promise<Response>,
) {
  return vi.fn((input: unknown, options?: RequestInit) => {
    const url = String(input);
    if (url.includes("/comments?"))
      return jsonResponse({ comments: [], has_more: false });
    if (url.includes("/board?")) return jsonResponse(board);
    if (url.includes("/history"))
      return jsonResponse({ entries: [], next_cursor: null });
    if (url.includes("/watchers")) return jsonResponse([]);
    if (url.includes("/members")) return jsonResponse([]);
    if (url.endsWith("/tasks/task-1") && options?.method === "PATCH" && patch)
      return patch(options);
    if (url.endsWith("/tasks/task-1"))
      return jsonResponse(board.columns.flatMap((column) => column.tasks)[0]);
    return jsonResponse([]);
  });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("task planning", () => {
  it("shows story points and highlights only overdue unfinished cards", async () => {
    const overdue = makeTask({ story_points: 8, due_date: "2020-01-01" });
    renderView(makeBoard(overdue));

    const card = await screen.findByRole("article", {
      name: "Open task task-1",
    });
    expect(within(card).getByText("8 SP")).toBeInTheDocument();
    expect(within(card).getByText(/Due/)).toHaveAttribute(
      "datetime",
      "2020-01-01",
    );
    expect(card).toHaveClass("overdue");

    cleanup();
    const completedBoard = makeBoard({ ...overdue, status_id: "status-done" });
    completedBoard.columns[0].tasks = [];
    completedBoard.columns[1].tasks = [
      { ...overdue, status_id: "status-done" },
    ];
    renderView(completedBoard);

    expect(
      await screen.findByRole("article", { name: "Open task task-1" }),
    ).not.toHaveClass("overdue");
  });

  it("shows completing state without an editable control on Kanban", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn((input: unknown) =>
        String(input).includes("/board?")
          ? jsonResponse(makeBoard())
          : jsonResponse([]),
      ),
    );
    renderView(makeBoard(), { id: "owner-1", email: "owner@example.com" });
    await screen.findByRole("heading", { name: "Done" });
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(
      screen.queryByRole("checkbox", { name: "Completing status" }),
    ).not.toBeInTheDocument();
  });

  it("renders planning fields read-only for an unrelated project member", async () => {
    const task = makeTask({
      reporter_id: "owner-1",
      assignee_id: "owner-1",
      story_points: 5,
      due_date: "2026-10-15",
    });
    renderView(makeBoard(task), {
      id: "member-1",
      email: "member@example.com",
    });

    await userEvent.click(
      await screen.findByRole("article", { name: "Open task task-1" }),
    );
    await waitFor(() =>
      expect(screen.queryByText("Loading task...")).not.toBeInTheDocument(),
    );
    expect(screen.queryByLabelText("Story points")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Deadline")).not.toBeInTheDocument();
    expect(screen.getAllByText("5 SP").length).toBeGreaterThan(0);
    expect(screen.getByText("Oct 15, 2026")).toBeInTheDocument();
  });

  it("submits and retains planning edits when a mutation fails", async () => {
    const task = makeTask({ story_points: 3, due_date: "2026-10-10" });
    const board = makeBoard(task);
    const fetchMock = createFetch(board, () =>
      jsonResponse({ detail: "Planning update denied" }, 403),
    );
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView
          project={testProject}
          currentUser={{ id: "owner-1", email: "owner@example.com" }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    await userEvent.click(
      await screen.findByRole("article", { name: "Open task task-1" }),
    );
    await userEvent.selectOptions(
      await screen.findByLabelText("Story points"),
      "8",
    );
    await userEvent.selectOptions(
      screen.getByLabelText("Priority"),
      "critical",
    );
    const deadline = screen.getByLabelText("Deadline");
    await userEvent.clear(deadline);
    await userEvent.type(deadline, "2026-10-20");
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Planning update denied",
    );
    expect(screen.getByLabelText("Story points")).toHaveValue("8");
    expect(screen.getByLabelText("Deadline")).toHaveValue("2026-10-20");
    expect(screen.getByLabelText("Priority")).toHaveValue("critical");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/tasks/task-1",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({
          title: "First task",
          description: "",
          story_points: 8,
          due_date: "2026-10-20",
          priority: "critical",
        }),
      }),
    );
  });

  it("shows profile names, compact participant rows, watcher icon and priority badge", async () => {
    const watcher = { id: "owner-1", first_name: "Olga", last_name: "Owner" };
    const task = makeTask({
      priority: "major",
      reporter: watcher,
      assignee_id: "member-1",
      assignee: { id: "member-1", first_name: "Max", last_name: "Member" },
      watchers: [watcher],
    });
    const board = makeBoard(task);
    const fetchMock = vi.fn((input: unknown) => {
      const url = String(input);
      if (url.includes("/comments?"))
        return jsonResponse({ comments: [], has_more: false });
      if (url.includes("/board?")) return jsonResponse(board);
      if (url.endsWith("/tasks/task-1/watchers"))
        return jsonResponse([watcher]);
      if (url.endsWith("/projects/project-1/members"))
        return jsonResponse([
          {
            id: "owner-1",
            email: "owner@example.com",
            is_active: true,
            profile: {
              user_id: "owner-1",
              first_name: "Olga",
              last_name: "Owner",
            },
          },
          {
            id: "member-1",
            email: "member@example.com",
            is_active: true,
            profile: {
              user_id: "member-1",
              first_name: "Max",
              last_name: "Member",
            },
          },
        ]);
      if (url.endsWith("/tasks/task-1")) return jsonResponse(task);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView
          project={testProject}
          currentUser={{ id: "owner-1", email: "owner@example.com" }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    const card = await screen.findByRole("article", {
      name: "Open task task-1",
    });
    expect(within(card).getByText("Major")).toHaveClass("priority-major");
    await userEvent.click(card);

    const reporter = await screen.findByLabelText("Reporter");
    expect(reporter).toHaveTextContent("Olga Owner");
    expect(screen.getByLabelText("Assignee")).toHaveTextContent("Max Member");
    expect(reporter.closest(".participant-row")).not.toBeNull();
    expect(
      screen.getByText("Olga Owner", { selector: ".watcher" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("owner@example.com")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Stop watching" }),
    ).toHaveAttribute("title", "Stop watching");
    expect(
      screen.getByLabelText("Status").closest(".task-field-row"),
    ).not.toBeNull();
    expect(screen.getByLabelText("Priority")).toHaveValue("major");
  });

  it("creates a task with an optional estimate and deadline", async () => {
    const board = makeBoard();
    const created: Task = makeTask({
      story_points: 13,
      due_date: "2026-11-01",
    });
    const fetchMock = vi.fn((input: unknown, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/board?")) return jsonResponse(board);
      if (
        url.endsWith("/projects/project-1/tasks") &&
        options?.method === "POST"
      ) {
        return jsonResponse(created, 201);
      }
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    render(
      <QueryClientProvider client={createTestQueryClient()}>
        <KanbanView
          project={testProject}
          currentUser={{ id: "owner-1", email: "owner@example.com" }}
          onClose={vi.fn()}
        />
      </QueryClientProvider>,
    );

    const backlogColumn = (
      await screen.findByRole("heading", { name: "Backlog" })
    ).closest("section");
    await userEvent.click(
      within(backlogColumn as HTMLElement).getByRole("button", {
        name: "Add task",
      }),
    );
    await userEvent.type(
      within(backlogColumn as HTMLElement).getByLabelText("Title"),
      "Planned task",
    );
    await userEvent.selectOptions(
      within(backlogColumn as HTMLElement).getByLabelText("Story points"),
      "13",
    );
    await userEvent.type(
      within(backlogColumn as HTMLElement).getByLabelText("Deadline"),
      "2026-11-01",
    );
    await userEvent.click(
      within(backlogColumn as HTMLElement).getByRole("button", {
        name: "Create",
      }),
    );

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/projects/project-1/tasks",
        expect.objectContaining({
          method: "POST",
          body: JSON.stringify({
            title: "Planned task",
            description: null,
            status_id: "status-backlog",
            story_points: 13,
            due_date: "2026-11-01",
            priority: null,
          }),
        }),
      ),
    );
  });
});
