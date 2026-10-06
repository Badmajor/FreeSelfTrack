import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { MembersPage } from "../MembersPage";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const owner = { id: "owner", email: "owner@example.com", is_active: true, profile: { user_id: "owner", first_name: "Anna", last_name: "Smith" } };
const member = { ...owner, id: "member", email: "member@example.com", profile: { user_id: "member", first_name: "Alex", last_name: "Jones" } };
const organization = { id: "org", name: "Team", capabilities: { manage_members: true } };
const project = { id: "project", organization_id: "org", name: "Tracker", capabilities: { manage_members: true } };
const props = { user: owner, organizations: [organization], projects: [project], organizationId: "org", projectId: "project", loading: false, error: "", onClose: vi.fn(), onOrganizationChange: vi.fn(), onProjectChange: vi.fn(), onProjectUpdated: vi.fn() };
function mount(overrides: Partial<typeof props> = {}) {
  const client = createTestQueryClient();
  return render(<QueryClientProvider client={client}><MembersPage {...props} {...overrides} /></QueryClientProvider>);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("adds organization and project members by email, confirms duplicates and displays profile names", async () => {
  const lists: Record<string, typeof owner[]> = { "/api/organizations/org/members": [owner], "/api/projects/project/members": [owner] };
  const fetchMock = vi.fn((input: unknown, options?: RequestInit) => {
    const url = String(input);
    if (options?.method === "POST") { if (!lists[url].some((item) => item.id === member.id)) lists[url].push(member); return jsonResponse(member); }
    return jsonResponse([...lists[url]]);
  });
  vi.stubGlobal("fetch", fetchMock); mount();
  expect(await screen.findByText("Anna Smith")).toBeInTheDocument();
  for (const scope of ["organization", "project"]) {
    if (scope === "project") await userEvent.click(screen.getByRole("button", { name: "Project members" }));
    for (let attempt = 0; attempt < 2; attempt++) {
      await userEvent.type(screen.getByLabelText("Email"), member.email);
      await userEvent.click(screen.getByRole("button", { name: "Add member" }));
      await screen.findByText("Membership confirmed.");
      await waitFor(() => expect(screen.getByRole("button", { name: "Add member" })).toBeEnabled());
      expect(screen.getAllByText("Alex Jones")).toHaveLength(1);
    }
    expect(fetchMock).toHaveBeenCalledWith(scope === "organization" ? "/api/organizations/org/members" : "/api/projects/project/members", expect.objectContaining({ method: "POST", body: JSON.stringify({ email: member.email }) }));
  }
});

it.each([[404, "User not found"], [409, "Project member must belong to the project organization"], [403, "Administrative permission required"]])("preserves email after %s errors and blocks duplicate requests while pending", async (status, message) => {
  let finish: (response: Response) => void = () => {};
  const fetchMock = vi.fn((_input: unknown, options?: RequestInit) => options?.method === "POST" ? new Promise<Response>((resolve) => { finish = resolve; }) : jsonResponse([]));
  vi.stubGlobal("fetch", fetchMock); mount();
  await screen.findByText("No members found.");
  const email = screen.getByLabelText("Email");
  await userEvent.type(email, member.email);
  await userEvent.click(screen.getByRole("button", { name: "Add member" }));
  expect(screen.getByRole("button", { name: "Adding..." })).toBeDisabled();
  finish(new Response(JSON.stringify({ detail: message }), { status: Number(status) }));
  expect(await screen.findByRole("alert")).toHaveTextContent(String(message));
  expect(email).toHaveValue(member.email);
});

it("uses organization and project capabilities independently", async () => {
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse([owner])));
  mount({ projects: [{ ...project, capabilities: { manage_members: false } }] });
  await screen.findByText("Anna Smith");
  expect(screen.getByRole("button", { name: "Add member" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Project members" }));
  await screen.findByText("Anna Smith");
  expect(screen.queryByRole("button", { name: "Add member" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Remove" })).not.toBeInTheDocument();
});

it("shows loading and permits retry after a list error", async () => {
  let finish: (response: Response) => void = () => {};
  vi.stubGlobal("fetch", vi.fn().mockImplementationOnce(() => new Promise<Response>((resolve) => { finish = resolve; })).mockImplementation(() => jsonResponse([])));
  mount(); expect(screen.getByText("Loading members...")).toBeInTheDocument();
  finish(new Response(JSON.stringify({ detail: "Unavailable" }), { status: 503 }));
  await screen.findByRole("alert");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No members found.")).toBeInTheDocument();
});

it("does not display the previous organization response after switching context", async () => {
  let finish: (response: Response) => void = () => {};
  vi.stubGlobal("fetch", vi.fn((input: unknown) => String(input).includes("/org/members") ? new Promise<Response>((resolve) => { finish = resolve; }) : jsonResponse([member])));
  const client = createTestQueryClient();
  const view = render(<QueryClientProvider client={client}><MembersPage {...props} /></QueryClientProvider>);
  view.rerender(<QueryClientProvider client={client}><MembersPage {...props} organizations={[{ ...organization, id: "other" }]} organizationId="other" projects={[]} projectId="" /></QueryClientProvider>);
  await screen.findByText("Alex Jones");
  await act(async () => { finish(new Response(JSON.stringify([owner]))); });
  expect(screen.queryByText("Anna Smith")).not.toBeInTheDocument();
  expect(screen.getByText("Alex Jones")).toBeInTheDocument();
});
