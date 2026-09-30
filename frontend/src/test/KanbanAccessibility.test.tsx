import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import { jsonResponse, makeBoard, makeTask, renderWithQueryClient, testProject } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("Kanban keyboard accessibility", () => {
  it("moves focus into the drawer and returns it to the task card on close", async () => {
    const task = makeTask();
    vi.stubGlobal("fetch", vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
      if (url.includes("/board?")) return jsonResponse(makeBoard(task));
      if (url.includes("/tasks/task-1/history")) return jsonResponse({ entries: [], next_cursor: null });
      if (url.includes("/tasks/task-1/watchers")) return jsonResponse([]);
      if (url.includes("/projects/project-1/members")) return jsonResponse([]);
      if (url.includes("/tasks/task-1")) return jsonResponse(task);
      return jsonResponse([]);
    }));

    renderWithQueryClient(
      <KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} />,
    );

    const card = await screen.findByRole("article", { name: "Open task task-1" });
    await userEvent.click(card);
    expect(await screen.findByLabelText("Title")).toHaveFocus();

    await userEvent.click(screen.getByRole("button", { name: "Close task details" }));
    await vi.waitFor(() => expect(card).toHaveFocus());
  });
});
