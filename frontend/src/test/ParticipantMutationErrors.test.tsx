import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { KanbanView } from "../KanbanView";
import { jsonResponse, makeBoard, makeTask, renderWithQueryClient, testProject } from "./test-utils";

const owner = { id: "owner-1", email: "owner@example.com" };
const member = { id: "member-1", email: "member@example.com" };

function createFetchMock(message: string, mutation: "watcher" | "reporter" | "assignee") {
  const task = makeTask();
  return vi.fn((input: string | URL | Request, options?: RequestInit) => {
    const url = String(input);
    if (url.includes("/board?")) return jsonResponse(makeBoard(task));
    if (url.includes("/tasks/task-1/watchers") && options?.method === "POST" && mutation === "watcher") {
      return jsonResponse({ detail: message }, 403);
    }
    if (url === "/api/tasks/task-1" && options?.method === "PATCH" && mutation !== "watcher") {
      return jsonResponse({ detail: message }, 403);
    }
    if (url.includes("/tasks/task-1/history")) return jsonResponse({ entries: [], next_cursor: null });
    if (url.includes("/tasks/task-1/watchers")) return jsonResponse([]);
    if (url.includes("/projects/project-1/members")) return jsonResponse([owner, member]);
    if (url.includes("/tasks/task-1")) return jsonResponse(task);
    return jsonResponse([]);
  });
}

function renderTask(fetchMock: ReturnType<typeof vi.fn>) {
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(
    <KanbanView project={testProject} currentUser={owner} onClose={vi.fn()} />,
  );
}

async function openTask() {
  await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));
  await screen.findByRole("dialog", { name: "Task details" });
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("participant mutation errors", () => {
  it("keeps the previous watcher state after a failed watch mutation", async () => {
    renderTask(createFetchMock("Watcher update denied", "watcher"));
    await openTask();

    await userEvent.click(await screen.findByRole("button", { name: "Watch task" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Watcher update denied");
    expect(screen.getByRole("button", { name: "Watch task" })).toBeInTheDocument();
  });

  it("restores the previous reporter after a failed mutation", async () => {
    renderTask(createFetchMock("Reporter update denied", "reporter"));
    await openTask();

    const reporter = screen.getByLabelText("Reporter");
    await userEvent.selectOptions(reporter, member.id);

    expect(await screen.findByRole("alert")).toHaveTextContent("Reporter update denied");
    await waitFor(() => expect(reporter).toHaveValue(owner.id));
  });

  it("restores the previous assignee after a failed mutation", async () => {
    renderTask(createFetchMock("Assignee update denied", "assignee"));
    await openTask();

    const assignee = screen.getByLabelText("Assignee");
    await userEvent.selectOptions(assignee, member.id);

    expect(await screen.findByRole("alert")).toHaveTextContent("Assignee update denied");
    await waitFor(() => expect(assignee).toHaveValue(""));
  });
});
