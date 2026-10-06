import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";

import { App } from "../App";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const user = { id: "owner-1", email: "owner@example.com", is_active: true };
const organization = { id: "organization-1", capabilities: { edit: true, manage_members: true, manage_workflow: true, archive: true }, name: "Acme" };
const project = {
  id: "project-1",
  organization_id: organization.id,
  capabilities: { edit: true, manage_members: true, manage_workflow: true, archive: true },
  name: "Tracker",
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

it("creates organizations and projects on separate management pages", async () => {
  let organizations: (typeof organization)[] = [];
  let projects: (typeof project)[] = [];
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh")) return jsonResponse({ access_token: "token", token_type: "bearer", user });
      if (url.endsWith("/organizations") && options?.method === "POST") {
        organizations = [organization];
        return jsonResponse(organization, 201);
      }
      if (url.endsWith("/organizations")) return jsonResponse(organizations);
      if (url.endsWith("/organizations/organization-1/projects"))
        return jsonResponse(projects);
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
    <MemoryRouter initialEntries={["/management/organizations"]}>
      <QueryClientProvider client={createTestQueryClient()}>
        <App />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  const actor = userEvent.setup();

  expect(
    await screen.findByRole("heading", { name: "Organizations" }),
  ).toBeInTheDocument();
  await actor.type(screen.getByLabelText("Name"), "Acme");
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
  await actor.type(screen.getByLabelText("Name"), "Tracker");
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
      }),
    }),
  );
});
