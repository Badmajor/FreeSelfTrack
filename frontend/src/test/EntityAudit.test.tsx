import { useState } from "react";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { EntityAudit } from "../EntityAudit";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const entry = {
  id: "one", occurred_at: "2026-01-01T12:00:00Z", operation_id: "operation",
  actor: { kind: "user", id: "actor", display_name: "Test Person" },
  entity: { type: "user", id: "target" }, action: "profile_updated", subject_user_id: null,
  changes: [{ field: "first_name", old: "Before", new: "After" }, { field: "last_name", old: "Old", new: "New" }],
};

it("renders an aggregated event, switches pages and refreshes from the first page", async () => {
  const fetchMock = vi.fn((input: string | URL | Request) => jsonResponse({
    items: String(input).includes("cursor=") ? [] : [entry],
    next_cursor: String(input).includes("cursor=") ? null : "next", page_size: 20,
  }));
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<EntityAudit scope="users" id="target" />);
  expect(await screen.findByText("Test Person")).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(1);
  expect(screen.getByText("Old: Before → New: After")).toBeInTheDocument();
  expect(screen.getByText("Old: Old → New: New")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Next audit page" }));
  expect(await screen.findByText("No audit entries.")).toBeInTheDocument();
  expect(screen.queryByText("Test Person")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Next audit page" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Previous audit page" }));
  expect(await screen.findByText("Test Person")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Next audit page" }));
  await screen.findByText("No audit entries.");
  await userEvent.click(screen.getByRole("button", { name: "Refresh audit" }));
  expect(await screen.findByText("Test Person")).toBeInTheDocument();
  expect(screen.getByText("Page 1")).toBeInTheDocument();
});

it("shows loading, error and retry without stale protected records", async () => {
  let resolve!: (response: Response) => void;
  const fetchMock = vi.fn().mockImplementationOnce(() => new Promise<Response>(r => { resolve = r; }));
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<EntityAudit scope="tasks" id="task" />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading audit");
  resolve(await jsonResponse({ detail: "Task not found" }, 404));
  expect(await screen.findByRole("alert")).toHaveTextContent("Task not found");
  fetchMock.mockImplementation(() => jsonResponse({ items: [], page_size: 20, next_cursor: null }));
  await userEvent.click(screen.getByRole("button", { name: "Retry audit" }));
  expect(await screen.findByText("No audit entries.")).toBeInTheDocument();
});

it("resets pagination when the selected entity changes", async () => {
  const fetchMock = vi.fn(() => jsonResponse({ items: [], page_size: 20, next_cursor: "next" }));
  vi.stubGlobal("fetch", fetchMock);
  function Selection() {
    const [id, setId] = useState("first");
    return <><button onClick={() => setId("second")}>Select second</button><EntityAudit scope="projects" id={id} /></>;
  }
  renderWithQueryClient(<Selection />);
  await screen.findByText("No audit entries.");
  await userEvent.click(screen.getByRole("button", { name: "Next audit page" }));
  await waitFor(() => expect(screen.getByText("Page 2")).toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Select second" }));
  expect(screen.getByText("Page 1")).toBeInTheDocument();
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/projects/second/audit"), expect.anything()));
});
