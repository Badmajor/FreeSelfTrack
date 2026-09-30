import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { KanbanView } from "../KanbanView";
import { createTestQueryClient, jsonResponse, makeBoard, makeTask, testProject } from "./test-utils";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it("submits from the header, blocks duplicate saves and retains edits on failure", async () => {
  let finish: (response: Response) => void = () => {};
  const fetchMock = vi.fn((input: unknown, options?: RequestInit) => {
    const url = String(input);
      if (url.includes("/comments?")) return Promise.resolve(new Response(JSON.stringify({ comments: [], has_more: false }), { status: 200 }));
    if (options?.method === "PATCH") return new Promise<Response>((resolve) => { finish = resolve; });
    if (url.includes("/board?")) return jsonResponse(makeBoard());
    if (url.endsWith("/tasks/task-1")) return jsonResponse(makeTask());
    if (url.includes("/history")) return jsonResponse({ entries: [], next_cursor: null });
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<QueryClientProvider client={createTestQueryClient()}><KanbanView project={testProject} currentUser={{ id: "owner-1", email: "owner@example.com" }} onClose={vi.fn()} /></QueryClientProvider>);
  await userEvent.click(await screen.findByRole("article", { name: "Open task task-1" }));
  await waitFor(() => expect(screen.queryByText("Loading task...")).not.toBeInTheDocument());
  await userEvent.clear(screen.getByLabelText("Title"));
  await userEvent.type(screen.getByLabelText("Title"), "Keep these edits");
  await userEvent.type(screen.getByLabelText("Message"), "Unsent draft");
  await userEvent.click(screen.getByRole("tab", { name: "History" }));
  await userEvent.click(screen.getByRole("tab", { name: "Chat" }));
  expect(screen.getByLabelText("Message")).toHaveValue("Unsent draft");
  await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
  const saving = screen.getByRole("button", { name: "Saving..." });
  expect(saving).toBeDisabled();
  await userEvent.click(saving);
  expect(fetchMock.mock.calls.filter((call) => call[1]?.method === "PATCH")).toHaveLength(1);
  finish(new Response(JSON.stringify({ detail: "Unable to save" }), { status: 500 }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to save");
  expect(screen.getByLabelText("Title")).toHaveValue("Keep these edits");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();
});
