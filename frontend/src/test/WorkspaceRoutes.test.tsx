import { QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { AuthenticatedApp } from "../WorkspaceApp";
import {
  createTestQueryClient,
  jsonResponse,
  makeBoard,
  makeTask,
} from "./test-utils";

const user = {
  id: "owner-1",
  email: "owner@example.com",
  is_active: true,
  profile: { user_id: "owner-1", first_name: "Owner", last_name: "User" },
};
const organization = { id: "organization-1", owner_id: user.id, name: "Acme" };
const project = {
  id: "project-1",
  organization_id: organization.id,
  owner_id: user.id,
  name: "Tracker",
};
const statuses = [
  {
    id: "backlog",
    project_id: project.id,
    name: "Backlog",
    position: 0,
    is_active: true,
    is_completed: false,
  },
  {
    id: "done",
    project_id: project.id,
    name: "Done",
    position: 1,
    is_active: true,
    is_completed: true,
  },
];

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

function mount(currentUser = user, currentProject = project) {
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/organizations")) return jsonResponse([organization]);
      if (url.endsWith("/organizations/organization-1/projects"))
        return jsonResponse([currentProject]);
      if (url.endsWith("/projects/project-1/statuses/archive"))
        return jsonResponse([]);
      if (
        url.endsWith("/projects/project-1/statuses/done") &&
        options?.method === "PATCH"
      )
        return jsonResponse(
          { detail: "At least one active completing status must remain" },
          409,
        );
      if (url.endsWith("/projects/project-1/statuses"))
        return jsonResponse(statuses);
      if (url.endsWith("/projects/project-1"))
        return jsonResponse(currentProject);
      if (url.includes("/notifications/unread-count"))
        return jsonResponse({ count: 2 });
      return jsonResponse([]);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/management/projects/project-1/workflow"]}>
      <QueryClientProvider client={createTestQueryClient()}>
        <AuthenticatedApp
          user={currentUser}
          onSignOut={vi.fn()}
          onUserSaved={vi.fn()}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return fetchMock;
}

it("restores workflow from its URL and persists collapsed sidebar with a project flyout", async () => {
  mount();
  expect(
    await screen.findByRole("heading", { name: "Tracker workflow" }),
  ).toBeInTheDocument();
  const doneRow = screen
    .getByDisplayValue("Done")
    .closest(".workflow-row") as HTMLElement;
  const completing = within(doneRow).getByRole("checkbox", {
    name: "Completing",
  });
  expect(completing).toBeChecked();
  await userEvent.click(completing);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "At least one active completing status must remain",
  );
  expect(completing).toBeChecked();

  await userEvent.click(
    screen.getByRole("button", { name: "Collapse sidebar" }),
  );
  expect(localStorage.getItem("freeselftrack.sidebar.collapsed")).toBe("true");
  await userEvent.click(screen.getByRole("button", { name: "Acme" }));
  expect(await screen.findByRole("menu")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Tracker" })).toHaveAttribute(
    "href",
    "/projects/project-1/kanban",
  );
  const trigger = screen.getByRole("button", { name: "Acme" });
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  expect(trigger).toHaveFocus();
});

it("renders workflow controls read-only for a project member", async () => {
  mount({ ...user, id: "member-1" }, { ...project, owner_id: "owner-1" });
  expect(
    await screen.findByText(
      "You can inspect this workflow. Only the project owner can change it.",
    ),
  ).toBeInTheDocument();
  await waitFor(() =>
    expect(
      screen
        .getAllByRole("checkbox")
        .every((checkbox) => checkbox.hasAttribute("disabled")),
    ).toBe(true),
  );
  expect(
    screen.queryByRole("button", { name: /Archive/ }),
  ).not.toBeInTheDocument();
  expect(screen.getByText("Archive")).toBeInTheDocument();
});

it("opens a notification on the addressable task route", async () => {
  const task = makeTask();
  const notification = {
    id: "notification-1",
    recipient_id: user.id,
    task_id: task.id,
    event_type: "status_changed",
    message: "Task changed",
    event_data: JSON.stringify({ project_id: project.id }),
    created_at: "2026-10-01T08:00:00Z",
    read_at: null,
  };
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/organizations")) return jsonResponse([organization]);
      if (url.endsWith("/notifications/unread-count"))
        return jsonResponse({ count: 1 });
      if (url.endsWith("/notifications/notification-1/open"))
        return jsonResponse({
          ...notification,
          read_at: "2026-10-01T08:01:00Z",
        });
      if (url.endsWith("/notifications")) return jsonResponse([notification]);
      if (url.endsWith("/tasks/task-1")) return jsonResponse(task);
      if (url.endsWith("/projects/project-1")) return jsonResponse(project);
      if (url.includes("/projects/project-1/board?"))
        return jsonResponse(makeBoard(task));
      if (url.endsWith("/projects/project-1/members"))
        return jsonResponse([user]);
      if (url.includes("/history?"))
        return jsonResponse({ entries: [], next_cursor: null });
      if (url.includes("/comments?"))
        return jsonResponse({ comments: [], has_more: false });
      if (url.endsWith("/watchers")) return jsonResponse([]);
      return jsonResponse([]);
    }),
  );
  render(
    <MemoryRouter initialEntries={["/notifications"]}>
      <QueryClientProvider client={createTestQueryClient()}>
        <AuthenticatedApp
          user={user}
          onSignOut={vi.fn()}
          onUserSaved={vi.fn()}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await userEvent.click(await screen.findByText("Task changed"));
  expect(
    await screen.findByRole("region", { name: "Tracker Kanban" }),
  ).toBeInTheDocument();
  expect(await screen.findByDisplayValue("First task")).toBeInTheDocument();
});
