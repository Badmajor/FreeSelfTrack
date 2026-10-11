import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MembersPage } from "../MembersPage";
import { AssigneeName } from "../KanbanView";
import { type Membership } from "../api";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const user = { id: "user", email: "test@example.com", is_active: true };
const candidate = { id: "candidate", first_name: "Alex", last_name: "Jones", is_active: true };
const organization = { id: "org", name: "Team", capabilities: { manage_members: true, manage_managers: true } };
const project = { id: "project", organization_id: "org", name: "Tracker", capabilities: { manage_members: true, manage_managers: false } };
const props = { user, organizations: [organization], projects: [project], organizationId: "org", projectId: "", loading: false, error: "", onClose: vi.fn(), onOrganizationChange: vi.fn(), onProjectChange: vi.fn(), onProjectUpdated: vi.fn() };
function mount(overrides: Partial<typeof props> = {}) {
  return render(<QueryClientProvider client={createTestQueryClient()}><MembersPage {...props} {...overrides} /></QueryClientProvider>);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("adds a manager by UUID, demotes without removing and removes from organization", async () => {
  let items: Membership[] = [];
  const fetchMock = vi.fn((input: unknown, options?: RequestInit) => {
    if (String(input).includes("/users?")) return jsonResponse({ items: [candidate], next_cursor: null });
    if (options?.method === "PUT") {
      items = [{ user: candidate, role: JSON.parse(String(options.body)).role, state: "active" }];
      return jsonResponse(items[0]);
    }
    if (options?.method === "DELETE") { items = []; return Promise.resolve(new Response(null, { status: 204 })); }
    return jsonResponse({ items, next_cursor: null });
  });
  vi.stubGlobal("fetch", fetchMock); vi.spyOn(window, "confirm").mockReturnValue(true); mount();
  await screen.findByRole("option", { name: "Alex Jones" });
  await userEvent.selectOptions(screen.getByLabelText("User"), "candidate");
  await userEvent.selectOptions(screen.getByLabelText("Role"), "manager");
  await userEvent.click(screen.getByRole("button", { name: "Add member" }));
  await screen.findByRole("button", { name: "Remove manager role" });
  expect(fetchMock).toHaveBeenCalledWith("/api/organizations/org/members/candidate", expect.objectContaining({ method: "PUT", body: JSON.stringify({ role: "manager" }) }));
  await userEvent.click(screen.getByRole("button", { name: "Remove manager role" }));
  await screen.findByRole("button", { name: "Make manager" });
  await userEvent.click(screen.getByRole("button", { name: "Remove" }));
  await screen.findByText("No members found.");
});

it("keeps selection on hierarchy failure and prevents duplicate submission", async () => {
  let finish: (value: Response) => void = () => {};
  vi.stubGlobal("fetch", vi.fn((input: unknown, options?: RequestInit) => options?.method === "PUT"
    ? new Promise<Response>(resolve => { finish = resolve; })
    : jsonResponse({ items: String(input).includes("/users?") ? [candidate] : [], next_cursor: null })));
  mount(); await screen.findByRole("option", { name: "Alex Jones" });
  await userEvent.selectOptions(screen.getByLabelText("User"), "candidate");
  await userEvent.click(screen.getByRole("button", { name: "Add member" }));
  expect(screen.getByRole("button", { name: "Saving..." })).toBeDisabled();
  finish(new Response(JSON.stringify({ detail: "Target must have a lower global role", code: "membership_hierarchy" }), { status: 403 }));
  expect(await screen.findByRole("alert")).toHaveTextContent("lower global role");
  expect(screen.getByLabelText("User")).toHaveValue("candidate");
});

it("opens project scope directly and hides manager controls for PM", async () => {
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ items: [{ user: candidate, role: "member", state: "active" }], next_cursor: null })));
  mount({ projectId: "project" });
  await screen.findByText("Tracker", { selector: "h2" });
  expect(screen.queryByLabelText("Role")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Make manager" })).not.toBeInTheDocument();
  expect(await screen.findByRole("button", { name: "Remove" })).toBeInTheDocument();
});

it("retries failed membership pages and loads another page", async () => {
  let failed = true;
  vi.stubGlobal("fetch", vi.fn((input: unknown) => {
    if (String(input).includes("/users?")) return jsonResponse({ items: [], next_cursor: null });
    if (failed) { failed = false; return Promise.resolve(new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 })); }
    return jsonResponse({ items: [{ user: { ...candidate, id: String(input).includes("cursor") ? "second" : "first" }, role: "member", state: "active" }], next_cursor: String(input).includes("cursor") ? null : "next" });
  }));
  mount(); await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  await userEvent.click(await screen.findByRole("button", { name: "More members" }));
  await waitFor(() => expect(screen.getAllByRole("button", { name: "Remove" })).toHaveLength(2));
});

it("strikes only contextual unavailability and clears after re-add", () => {
  const view = render(<AssigneeName participant={{ ...candidate, unavailable_reasons: ["project_membership_revoked"] }} />);
  expect(screen.getByText("Alex Jones").tagName).toBe("S");
  expect(screen.getByText("(Removed from project)")).toBeInTheDocument();
  expect(screen.queryByText("(Blocked)")).not.toBeInTheDocument();
  view.rerender(<AssigneeName participant={{ ...candidate, unavailable_reasons: [] }} />);
  expect(screen.getByText("Alex Jones").tagName).toBe("SPAN");
});
