import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import { jsonResponse, makeBoard, makeTask, renderWithQueryClient, testProject } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Kanban async states", () => {
  it("shows loading state while the board request is pending", async () => {
    let resolveRequest: (value: Response) => void = () => undefined;
    const pending = new Promise<Response>((resolve) => { resolveRequest = resolve; });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));

    renderWithQueryClient(<KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} />);

    expect(screen.getByText("Loading Kanban...")).toBeInTheDocument();
    resolveRequest(new Response(JSON.stringify(makeBoard()), { status: 200 }));
    expect(await screen.findByText("First task")).toBeInTheDocument();
  });

  it("shows a retryable board error", async () => {
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new Error("Network unavailable"))
      .mockResolvedValueOnce(new Response(JSON.stringify(makeBoard()), { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} />);

    expect(await screen.findByRole("alert")).toHaveTextContent("Network unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("First task")).toBeInTheDocument();
  });

  it("shows an empty state for a column without tasks", async () => {
    const emptyBoard = makeBoard(makeTask({ id: "unused" }));
    emptyBoard.columns[0].tasks = [];
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(jsonResponse(emptyBoard)));

    renderWithQueryClient(<KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} />);

    expect(await screen.findAllByText("No tasks in this column.")).toHaveLength(2);
  });

  it("shows a watcher error in the task drawer", async () => {
    const task = makeTask();
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/board?")) return jsonResponse(makeBoard(task));
      if (url.includes("/tasks/task-1/history")) return jsonResponse({ entries: [], next_cursor: null });
      if (url.includes("/tasks/task-1/watchers")) return Promise.reject(new Error("Watchers unavailable"));
      if (url.includes("/tasks/task-1")) return jsonResponse(task);
      if (url.includes("/projects/project-1/members")) return jsonResponse([{ id: "owner-1", email: "owner@example.com" }]);
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderWithQueryClient(<KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} />);
    await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));

    expect(await screen.findByText("Unable to load watchers.")).toBeInTheDocument();
  });
});
