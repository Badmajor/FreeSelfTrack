import { transferableAbortController } from "node:util";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { App } from "../App";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const user = { id: "owner-1", email: "owner@example.com", is_active: true, is_system_admin: true };
const organization = { id: "organization-1", capabilities: { create_project: true, edit: true, manage_members: true, manage_workflow: true, archive: true }, name: "Acme" };
const project = {
  id: "project-1",
  organization_id: organization.id,
  capabilities: { create_project: true, edit: true, manage_members: true, manage_workflow: true, archive: true },
  name: "Tracker",
};

// Keep the controller compatible with Node’s Request used by the data router.
beforeEach(() => {
  vi.stubGlobal("AbortController", function () { return transferableAbortController(); });
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  window.localStorage.clear();
});

it("creates organizations and projects on separate management pages", async () => {
  let organizations: (typeof organization)[] = [];
  let projects: (typeof project)[] = [];
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.includes("/members")) return jsonResponse({ items: [{ user: { id: "candidate", first_name: "Alex", last_name: "Jones", is_active: true }, role: "member", state: "active" }], next_cursor: null });
      if (url.endsWith("/auth/refresh")) return jsonResponse({ access_token: "token", token_type: "bearer", user });
      if (url.endsWith("/organizations") && options?.method === "POST") {
        organizations = [organization];
        return jsonResponse(organization, 201);
      }
      if (url.endsWith("/organizations/organization-1")) return jsonResponse(organization);
      if (url.endsWith("/organizations")) return jsonResponse({ items: organizations, next_cursor: null });
      if (url.endsWith("/organizations/organization-1/projects"))
        return jsonResponse({ items: projects, next_cursor: null });
      if (url === "/api/projects" && options?.method === "POST") {
        projects = [project];
        return jsonResponse(project, 201);
      }
      if (url.endsWith("/projects/project-1")) return jsonResponse(project);
      if (url.includes("/notifications/unread-count"))
        return jsonResponse({ count: 0 });
      return jsonResponse([]);
    },
  );
  vi.stubGlobal("fetch", fetchMock);


  render(
    <QueryClientProvider client={createTestQueryClient()}>
      <RouterProvider router={createMemoryRouter([{ path: "*", element: <App /> }], { initialEntries: ["/management/organizations"] })} />
    </QueryClientProvider>,
  );
  const actor = userEvent.setup();

  expect(
    await screen.findByRole("heading", { name: "Organizations" }),
  ).toBeInTheDocument();
  await actor.click(screen.getByRole("link", { name: "Create organization" }));
  await actor.type(await screen.findByLabelText("Name"), "Acme");
  await actor.type(screen.getByLabelText("Description"), "Organization details");
  await actor.click(
    screen.getByRole("button", { name: /Create organization/ }),
  );
  expect(
    await screen.findByRole("heading", { name: "Acme" }),
  ).toBeInTheDocument();

  await actor.click(screen.getByRole("link", { name: "Project management" }));
  expect(
    await screen.findByRole("heading", { name: "Projects", level: 1 }),
  ).toBeInTheDocument();
  await actor.click(await screen.findByRole("link", { name: "Create project" }));
  await actor.type(await screen.findByLabelText("Name"), "Tracker");
  await actor.type(screen.getByLabelText("Description"), "Project details");
  await actor.click(await screen.findByRole("checkbox", { name: "Alex Jones" }));
  await actor.click(screen.getByRole("button", { name: /Create project/ }));
  expect(
    await screen.findByRole("heading", { name: "Tracker" }),
  ).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/projects",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        organization_id: organization.id,
        name: "Tracker",
        description: "Project details",
        manager_ids: ["candidate"],
      }),
    }),
  );
  // The separate project card preserves the API contract.
  await actor.clear(screen.getByLabelText("Name"));
  await actor.type(screen.getByLabelText("Name"), "Renamed project");
  await actor.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith("/api/projects/project-1", expect.objectContaining({
    method: "PATCH", body: JSON.stringify({ name: "Renamed project", description: null }),
  }));

});
