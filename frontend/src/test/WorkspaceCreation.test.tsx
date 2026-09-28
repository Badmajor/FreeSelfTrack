import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { createTestQueryClient, jsonResponse } from "./test-utils";
import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";

const user = { id: "owner-1", email: "owner@example.com", is_active: true };
const organization = { id: "organization-1", owner_id: user.id, name: "Acme" };
const project = { id: "project-1", organization_id: organization.id, owner_id: user.id, name: "Tracker" };

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("workspace creation", () => {
  it("creates an organization and then a project in it", async () => {
    const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/organizations") && options?.method === "POST") return jsonResponse(organization, 201);
      if (url.endsWith("/organizations")) return jsonResponse([]);
      if (url.endsWith("/organizations/organization-1/projects") && options?.method === "GET") return jsonResponse([]);
      if (url === "/api/projects" && options?.method === "POST") return jsonResponse(project, 201);
      if (url.endsWith("/projects/project-1/members")) return jsonResponse([user]);
      if (url.includes("/notifications/unread-count")) return jsonResponse({ count: 0 });
      return jsonResponse([]);
    });
    vi.stubGlobal("fetch", fetchMock);
    window.localStorage.setItem("freeselftrack.access_token", "token");
    window.localStorage.setItem("freeselftrack.user", JSON.stringify(user));
    const { App } = await import("../App");
    const actor = userEvent.setup();

    render(<QueryClientProvider client={createTestQueryClient()}><App /></QueryClientProvider>);

    await screen.findByRole("heading", { name: "No project selected" });
    await actor.click(screen.getByRole("button", { name: "New organization" }));
    await actor.type(screen.getByLabelText("Name"), "Acme");
    await actor.click(screen.getByRole("button", { name: "Create organization" }));

    expect(await screen.findByRole("option", { name: "Acme" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/organizations",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ name: "Acme" }) }),
    );

    await actor.click(await screen.findByRole("button", { name: "New project" }));
    await actor.type(screen.getByLabelText("Name"), "Tracker");
    await actor.click(screen.getByRole("button", { name: "Create project" }));

    expect(await screen.findByRole("heading", { name: "Tracker" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/projects",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ organization_id: organization.id, name: "Tracker" }) }),
    );
  });
});
