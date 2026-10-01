import { act, cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";

import * as api from "../api";
import { TaskLinks } from "../TaskLinks";
import { renderWithQueryClient } from "./test-utils";

const target = (id: string, project: string): api.TaskLinkTask => ({
  id,
  slug: "TWI-1",
  title: "Shared number",
  project_id: project,
  project_name: project === "project-a" ? "Alpha" : "Beta",
  status_id: "status",
  status_name: "Backlog",
});

const link = (relation: api.TaskLinkRelation): api.TaskLink => ({
  id: "link-1",
  relation_type: relation,
  task: target("target-1", "project-a"),
  created_by: { id: "owner", first_name: "Owner", last_name: "User" },
  created_at: "2026-10-01T10:00:00Z",
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it("disambiguates slug matches by project and creates the selected relation", async () => {
  vi.spyOn(api, "listTaskLinks").mockResolvedValue([]);
  vi.spyOn(api, "searchOrganizationTasks").mockResolvedValue({
    items: [target("target-1", "project-a"), target("target-2", "project-b")],
  });
  const create = vi
    .spyOn(api, "createTaskLink")
    .mockResolvedValue(link("blocks"));

  renderWithQueryClient(
    <TaskLinks
      taskId="source"
      taskSlug="SRC-1"
      projectId="source-project"
      organizationId="organization"
      canManage
      onOpenTask={vi.fn()}
      onStartSelection={vi.fn()}
    />,
  );

  await userEvent.selectOptions(
    screen.getByLabelText("Relationship"),
    "blocks",
  );
  await userEvent.type(screen.getByLabelText("Task number"), "twi-1");
  expect(screen.queryByRole("button", { name: "Find" })).not.toBeInTheDocument();

  expect(await screen.findByText("Alpha · Backlog")).toBeInTheDocument();
  expect(screen.getByText("Beta · Backlog")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", {
      name: /TWI-1 Shared number Alpha/,
    }),
  );
  expect(create).toHaveBeenCalledWith("source", "target-1", "blocks");
});

it("shows relative links to read-only users and opens the linked task", async () => {
  vi.spyOn(api, "listTaskLinks").mockResolvedValue([link("depends_on")]);
  const open = vi.fn();

  renderWithQueryClient(
    <TaskLinks
      taskId="source"
      taskSlug="SRC-1"
      projectId="source-project"
      organizationId="organization"
      canManage={false}
      onOpenTask={open}
      onStartSelection={vi.fn()}
    />,
  );

  expect(await screen.findByText("Depends on")).toBeInTheDocument();
  await userEvent.click(
    screen.getByRole("button", { name: /TWI-1 Shared number Alpha/ }),
  );
  expect(open).toHaveBeenCalledWith("project-a", "target-1");
  expect(screen.queryByLabelText("Relationship")).not.toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: /Remove link/ }),
  ).not.toBeInTheDocument();
});

it("keeps async failures visible and retryable", async () => {
  const read = vi
    .spyOn(api, "listTaskLinks")
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce([]);

  renderWithQueryClient(
    <TaskLinks
      taskId="source"
      taskSlug="SRC-1"
      projectId="source-project"
      organizationId="organization"
      canManage
      onOpenTask={vi.fn()}
      onStartSelection={vi.fn()}
    />,
  );

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to load links.",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry links" }));
  expect(await screen.findByText("No linked tasks.")).toBeInTheDocument();
  expect(read).toHaveBeenCalledTimes(2);
});

function renderSearch(onStartSelection = vi.fn()) {
  vi.spyOn(api, "listTaskLinks").mockResolvedValue([]);
  return renderWithQueryClient(
    <TaskLinks taskId="source" taskSlug="SRC-1" projectId="source-project"
      organizationId="organization" canManage onOpenTask={vi.fn()}
      onStartSelection={onStartSelection} />,
  );
}

it("searches automatically from three trimmed characters and hides matches on shortening", async () => {
  const search = vi.spyOn(api, "searchOrganizationTasks").mockResolvedValue({
    items: [target("source", "project-a"), target("target", "project-b")],
  });
  renderSearch();
  const input = screen.getByLabelText("Task number");
  await userEvent.type(input, "  tw");
  await act(() => new Promise((resolve) => setTimeout(resolve, 300)));
  expect(search).not.toHaveBeenCalled();
  await userEvent.type(input, "i");
  expect(await screen.findByText("Beta · Backlog")).toBeInTheDocument();
  expect(search).toHaveBeenCalledWith("organization", "twi");
  expect(screen.queryByText("Alpha · Backlog")).not.toBeInTheDocument();
  await userEvent.keyboard("{Backspace}");
  expect(screen.queryByRole("list", { name: "Matching tasks" })).not.toBeInTheDocument();
  expect(screen.queryByText("No matching tasks.")).not.toBeInTheDocument();
});

it("does not show a late response for a previous query", async () => {
  let resolveOld!: (value: { items: api.TaskLinkTask[] }) => void;
  const search = vi.spyOn(api, "searchOrganizationTasks")
    .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
    .mockResolvedValueOnce({ items: [target("new", "project-b")] });
  renderSearch();
  const input = screen.getByLabelText("Task number");
  await userEvent.type(input, "old");
  await waitFor(() => expect(search).toHaveBeenCalledWith("organization", "old"));
  expect(screen.getByText("Searching...")).toBeInTheDocument();
  await userEvent.clear(input);
  await userEvent.type(input, "new");
  expect(await screen.findByText("Beta · Backlog")).toBeInTheDocument();
  await act(async () => resolveOld({ items: [target("old", "project-a")] }));
  expect(screen.queryByText("Alpha · Backlog")).not.toBeInTheDocument();
});

it("shows search errors and empty results for the current input", async () => {
  vi.spyOn(api, "searchOrganizationTasks")
    .mockRejectedValueOnce(new Error("Search unavailable"))
    .mockResolvedValueOnce({ items: [] });
  renderSearch();
  const input = screen.getByLabelText("Task number");
  await userEvent.type(input, "bad");
  expect(await screen.findByRole("alert")).toHaveTextContent("Search unavailable");
  await userEvent.clear(input);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  await userEvent.type(input, "none");
  expect(await screen.findByText("No matching tasks.")).toBeInTheDocument();
});

it("starts board selection from an accessible icon with the selected relation", async () => {
  const start = vi.fn();
  renderSearch(start);
  await userEvent.selectOptions(screen.getByLabelText("Relationship"), "depends_on");
  const button = screen.getByRole("button", { name: "Select on board" });
  expect(button).toHaveAttribute("title", "Select on board");
  expect(button.textContent).toBe("");
  button.focus();
  await userEvent.keyboard("{Enter}");
  expect(start).toHaveBeenCalledWith({ sourceTaskId: "source", sourceSlug: "SRC-1",
    sourceProjectId: "source-project", organizationId: "organization", relationType: "depends_on" });
});
