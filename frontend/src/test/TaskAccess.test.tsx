import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { KanbanView } from "../KanbanView";
import { jsonResponse, makeBoard, makeTask, renderWithQueryClient, testProject } from "./test-utils";

function mount(edit: boolean) {
  const task = makeTask({ capabilities: { edit, comment: true, watch: edit, link: edit } });
  const fetch = vi.fn((input: unknown, options?: RequestInit) => {
    const url = String(input);
    if (url.includes("/participants")) return jsonResponse({ items: [{ id: "owner-1", first_name: "Owner", last_name: "User" }], next_cursor: null });
    if (url.includes("/members")) return jsonResponse({ items: [{ user: { id: "owner-1", first_name: "Owner", last_name: "User" }, state: "active", role: "member" }], next_cursor: null });
    if (url.includes("/board?")) return jsonResponse(makeBoard(task));
    if (url.includes("/comments")) {
      if (options?.method === "POST") return jsonResponse({ detail: "Task access revoked" }, 404);
      return jsonResponse({ comments: [], has_more: false });
    }
    if (url.endsWith("/tasks") && options?.method === "POST") return jsonResponse(task, 201);
    if (url.endsWith("/tasks/task-1")) return jsonResponse(task);
    if (url.endsWith("/watchers")) return jsonResponse([]);
    if (url.includes("/history")) return jsonResponse({ entries: [], next_cursor: null });
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetch);
  renderWithQueryClient(<KanbanView project={{...testProject, capabilities: { create_task: edit }}} currentUser={{ id: "other-member", email: "member@example.com" }} />);
  return fetch;
}

afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("lets an unrelated project member edit all fields using backend capabilities", async () => {
  mount(true);
  await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));
  expect(await screen.findByLabelText("Reporter")).toBeEnabled();
  expect(screen.getByLabelText("Assignee")).toBeEnabled();
  expect(screen.getByLabelText("Story points")).toBeEnabled();
  expect(screen.getByLabelText("Priority")).toBeEnabled();
});

it("allows a reader to comment without field editing and handles revoked access", async () => {
  mount(false);
  const card = await screen.findByRole("article", { name: "Open task task-1" });
  expect(card).toHaveAttribute("draggable", "false");
  await userEvent.click(card);
  expect(await screen.findByLabelText("Title")).toHaveAttribute("readonly");
  expect(screen.getByLabelText("Reporter")).toBeDisabled();
  expect(screen.queryByRole("button", { name: "Save changes" })).not.toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Message"), "Read-only discussion");
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(screen.queryByLabelText("Message")).not.toBeInTheDocument());
  expect(screen.getByText("Task access revoked")).toBeInTheDocument();
});

it("lets a manager outside membership explicitly choose a reporter when creating", async () => {
  const fetch = mount(true);
  await screen.findByRole("article", { name: "Open task task-1" });
  await userEvent.click(screen.getAllByRole("button", { name: "Add task" })[0]);
  await userEvent.type(screen.getByLabelText("Title"), "Created by a manager");
  await userEvent.selectOptions(await screen.findByLabelText("Reporter"), "owner-1");
  await userEvent.click(screen.getByRole("button", { name: "Create" }));
  await waitFor(() => expect(fetch.mock.calls.some(([url, options]) => String(url).endsWith("/tasks") && options?.method === "POST" && JSON.parse(String(options.body)).reporter_id === "owner-1")).toBe(true));
});
