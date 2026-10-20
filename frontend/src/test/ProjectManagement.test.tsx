import { transferableAbortController } from "node:util";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthenticatedApp } from "../WorkspaceApp";
import type { Project } from "../api";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const admin = { id: "admin", email: "admin@example.com", is_active: true, is_system_admin: true };
const org = { id: "one", name: "First organization", capabilities: { create_project: true } };
const otherOrg = { ...org, id: "two", name: "Second organization" };
const initial: Project = { id: "p", organization_id: "one", name: "First project", description: "Original description", capabilities: { edit: true, archive: true, view_audit: true } };
const second = { ...initial, id: "p2", name: "Second project" };
const other = { ...initial, id: "other", organization_id: "two", name: "Other project" };
const page = (items: unknown[], next_cursor: string | null = null) => ({ items, next_cursor });
let resource: Project;
let detailFailure: number, patchFailure: number, archiveFailure: number, createFailure: number, orgFailure: number;
let listFailure: boolean, nextFailure: boolean, auditFailure: boolean, empty: boolean, createAllowed: boolean;
let patchWait: Promise<Response> | undefined, archiveWait: Promise<Response> | undefined, createWait: Promise<Response> | undefined;
let auditCount: number;
let auditWait: Promise<Response> | undefined;
function mount(path = "/management/projects/p") {
  const fetchMock = vi.fn((input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.includes("unread-count")) return jsonResponse({ count: 0 });
    if (url.includes("/audit")) {
      auditCount++;
      if (auditWait) return auditWait;
      if (auditFailure) return jsonResponse({ detail: "Audit unavailable" }, 503);
      return jsonResponse({ ...page([{ id: url.includes("cursor") ? "event2" : "event1", action: "unknown_action", actor: { display_name: "Example actor" }, occurred_at: "2026-10-19T10:00:00Z", subject_user_id: "subject-id", operation_id: "operation-id", changes: [{ field: "description", old: "Before", new: "After" }] }], url.includes("cursor") ? null : "next-audit"), page_size: 20 });
    }
    if (url.endsWith("/archive")) {
      if (archiveWait) return archiveWait;
      if (archiveFailure) return jsonResponse({ detail: "Archive denied" }, archiveFailure);
      empty = true; return jsonResponse({ ...resource, archived_at: "2026-10-19" });
    }
    if (init?.method === "PATCH") {
      if (patchWait) return patchWait;
      if (patchFailure) return jsonResponse({ detail: "Save denied" }, patchFailure);
      resource = { ...resource, ...JSON.parse(String(init.body)) }; return jsonResponse(resource);
    }
    if (url === "/api/projects" && init?.method === "POST") {
      if (createWait) return createWait;
      if (createFailure) return jsonResponse({ detail: "Create denied" }, createFailure);
      resource = { ...initial, ...JSON.parse(String(init.body)), id: "created" }; empty = false; return jsonResponse(resource, 201);
    }
    if (url.includes("/members")) return jsonResponse(page([{ user: { id: url.includes("cursor") ? "m2" : "m1", first_name: url.includes("cursor") ? "Second" : "First", last_name: "Candidate", is_active: true }, role: "member", state: "active" }], url.includes("cursor") ? null : "next-members"));
    if (url.includes("/organizations/one/projects")) {
      if (listFailure || (nextFailure && url.includes("cursor"))) return jsonResponse({ detail: "List unavailable" }, 503);
      return jsonResponse(page(empty ? [] : url.includes("cursor") ? [second] : [resource], empty || url.includes("cursor") ? null : "next-project"));
    }
    if (url.includes("/organizations/two/projects")) return jsonResponse(page([other]));
    if (url === "/api/projects/p2") return jsonResponse(second);
    if (url === "/api/projects/other") return jsonResponse(other);
    if (url.startsWith("/api/projects/")) return detailFailure ? jsonResponse({ detail: "Detail unavailable" }, detailFailure) : jsonResponse(resource);
    if (url === "/api/organizations/one") return orgFailure ? jsonResponse({ detail: "Organization denied" }, orgFailure) : jsonResponse({ ...org, capabilities: { create_project: createAllowed } });
    if (url === "/api/organizations/two") return jsonResponse(otherOrg);
    if (url.includes("/organizations")) return jsonResponse(page([{ ...org, capabilities: { create_project: createAllowed } }, otherOrg]));
    return jsonResponse(page([]));
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = createTestQueryClient();
  const router = createMemoryRouter([{ path: "*", element: <AuthenticatedApp user={admin} onSignOut={vi.fn()} onUserSaved={vi.fn()} /> }], { initialEntries: [path] });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return { actor: userEvent.setup(), client, router, fetchMock };
}
beforeEach(() => {
  vi.stubGlobal("AbortController", function () { return transferableAbortController(); });
  resource = { ...initial }; detailFailure = patchFailure = archiveFailure = createFailure = orgFailure = auditCount = 0;
  listFailure = nextFailure = auditFailure = empty = false; createAllowed = true;
  patchWait = archiveWait = createWait = auditWait = undefined;
});
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear(); });
const card = () => within(screen.getByRole("region", { name: "Selected project" }));

it("puts working links and details first with history and identifiers closed and no audit fetch", async () => {
  mount(); await screen.findByLabelText("Name");
  expect(screen.getByLabelText("Name")).toHaveValue("First project");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(card().getByRole("link", { name: "Open Kanban" })).toHaveAttribute("href", "/projects/p/kanban");
  expect(card().getByText("First organization")).toBeInTheDocument();
  expect(screen.getByText("Change history").closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText("Technical details").closest("details")).not.toHaveAttribute("open");
  expect(auditCount).toBe(0);
  expect(screen.getByRole("link", { name: "Create project" })).toHaveAttribute("href", "/management/projects/new?organization=one");
});

it("preserves drafts across background refresh, cancels to latest data and refreshes card/catalog/sidebar after save", async () => {
  const { actor, client } = mount(); await screen.findByLabelText("Name");
  await actor.clear(screen.getByLabelText("Name")); await actor.type(screen.getByLabelText("Name"), "Draft");
  resource = { ...resource, name: "Server name" };
  await act(async () => { await client.invalidateQueries({ queryKey: ["project", "p"] }); });
  expect(screen.getByLabelText("Name")).toHaveValue("Draft");
  await actor.click(screen.getByRole("button", { name: "Cancel changes" })); expect(screen.getByLabelText("Name")).toHaveValue("Server name");
  await actor.clear(screen.getByLabelText("Name")); await actor.type(screen.getByLabelText("Name"), "  Saved project  ");
  await actor.click(screen.getByRole("button", { name: "Save changes" })); await screen.findByText("Changes saved.");
  expect(screen.getByRole("heading", { name: "Saved project" })).toBeInTheDocument();
  expect(within(screen.getByRole("navigation", { name: "Available projects" })).getByRole("link", { name: "Saved project" })).toBeInTheDocument();
  expect(document.querySelector(".sidebar-nav")?.textContent).toContain("Saved project");
});

it("validates trimmed name, retains failed input and blocks duplicate pending saves", async () => {
  const { actor, fetchMock } = mount(); await screen.findByLabelText("Name");
  expect(screen.getByLabelText("Name")).toHaveAttribute("maxlength", "200");
  await actor.clear(screen.getByLabelText("Name")); await actor.type(screen.getByLabelText("Name"), "   ");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await actor.type(screen.getByLabelText("Name"), "Draft"); patchFailure = 403;
  await actor.click(screen.getByRole("button", { name: "Save changes" })); await screen.findByRole("alert");
  expect(screen.getByLabelText("Name")).toHaveValue("   Draft");
  let resolve!: (response: Response) => void; patchWait = new Promise(r => { resolve = r; });
  await actor.dblClick(screen.getByRole("button", { name: "Save changes" }));
  expect(screen.getByRole("button", { name: "Saving changes…" })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2);
  await act(async () => resolve(await jsonResponse({ ...resource, name: "Draft" })));
  await screen.findByText("Changes saved.");
});

it("guards organization switching and browser history, keeping the previous selection on cancellation", async () => {
  const { actor, router } = mount(); await screen.findByLabelText("Name");
  await actor.type(screen.getByLabelText("Name"), " draft");
  const event = new Event("beforeunload", { cancelable: true }); window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);
  await actor.selectOptions(screen.getByLabelText("Organization"), "two");
  expect(await screen.findByRole("dialog")).toHaveTextContent("Discard unsaved changes?");
  await actor.click(screen.getByRole("button", { name: "Stay on page" }));
  expect(router.state.location.pathname).toBe("/management/projects/p"); expect(screen.getByLabelText("Organization")).toHaveValue("one");
  await actor.selectOptions(screen.getByLabelText("Organization"), "two"); await actor.click(screen.getByRole("button", { name: "Discard changes" }));
  expect(router.state.location.pathname).toBe("/management/projects"); expect(router.state.location.search).toBe("?organization=two");
  await screen.findByRole("link", { name: "Other project" }); expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  await act(async () => { await router.navigate(-1); }); await screen.findByLabelText("Name");
  await actor.type(screen.getByLabelText("Name"), " draft"); await act(async () => { await router.navigate(1); });
  await actor.click(screen.getByRole("button", { name: "Stay on page" })); expect(screen.getByLabelText("Name")).toHaveValue("First project draft");
});

it.each(["Open Kanban", "Workflow", "Members"])("guards dirty navigation to %s", async link => {
  const { actor, router } = mount(); await screen.findByLabelText("Name"); await actor.type(screen.getByLabelText("Name"), " draft");
  await actor.click(card().getByRole("link", { name: link }));
  await actor.click(screen.getByRole("button", { name: "Stay on page" }));
  expect(router.state.location.pathname).toBe("/management/projects/p"); expect(screen.getByLabelText("Name")).toHaveValue("First project draft");
});

it("loads history on demand, exposes all details, paginates, refreshes and stops observing when closed", async () => {
  const { actor, client } = mount(); await screen.findByLabelText("Name");
  await actor.click(screen.getByText("Change history")); await screen.findByText("unknown action");
  expect(screen.getByText("Details").closest("details")).not.toHaveAttribute("open");
  await actor.click(screen.getByText("Details"));
  expect(screen.getByText("Before")).toBeVisible(); expect(screen.getByText("After")).toBeVisible(); expect(screen.getByText("operation-id")).toBeVisible(); expect(screen.getByText("Member: subject-id")).toBeVisible();
  await actor.click(screen.getByRole("button", { name: "Next audit page" })); await screen.findByText("Page 2");
  await actor.click(screen.getByRole("button", { name: "Previous audit page" })); await screen.findByText("Page 1");
  await actor.click(screen.getByRole("button", { name: "Next audit page" })); await screen.findByText("Page 2");
  await actor.click(screen.getByRole("button", { name: "Refresh audit" })); await screen.findByText("Page 1");
  await actor.click(screen.getByText("Change history")); await waitFor(() => expect(screen.queryByRole("region", { name: "Administrative audit" })).not.toBeInTheDocument());
  const count = auditCount; await act(async () => { await client.invalidateQueries({ queryKey: ["entity-audit"] }); }); expect(auditCount).toBe(count);
  await actor.click(screen.getByText("Change history")); await screen.findByText("unknown action"); expect(auditCount).toBe(count + 1); expect(screen.getByText("Page 1")).toBeInTheDocument();
  await actor.click(screen.getByRole("button", { name: "Load more projects" }));
  await actor.click(within(screen.getByRole("navigation", { name: "Available projects" })).getByRole("link", { name: "Second project" }));
  await screen.findByRole("heading", { name: "Second project" }); expect(screen.getByText("Change history").closest("details")).not.toHaveAttribute("open");
});

it("keeps details usable on audit error and removes audit on capability revocation", async () => {
  const { actor, client } = mount(); await screen.findByLabelText("Name"); auditFailure = true;
  await actor.click(screen.getByText("Change history")); await screen.findByText("Audit unavailable");
  await actor.type(screen.getByLabelText("Name"), " changed"); await actor.click(screen.getByRole("button", { name: "Save changes" })); await screen.findByText("Changes saved.");
  auditFailure = false; await actor.click(screen.getByRole("button", { name: "Retry audit" })); await screen.findByText("unknown action");
  resource = { ...resource, capabilities: { ...resource.capabilities, view_audit: false } };
  await act(async () => { await client.invalidateQueries({ queryKey: ["project", "p"] }); });
  await waitFor(() => expect(screen.queryByText("Change history")).not.toBeInTheDocument()); expect(screen.queryByText("Example actor")).not.toBeInTheDocument();
});

it("retains the first catalog page on next-page failure and selects a direct project outside that page", async () => {
  const { actor } = mount("/management/projects/p2"); await screen.findByLabelText("Name");
  expect(within(screen.getByRole("navigation", { name: "Available projects" })).getByRole("link", { name: "Second project" })).toHaveAttribute("aria-current", "page");
  nextFailure = true; await actor.click(await screen.findByRole("button", { name: "Load more projects" })); await screen.findByText("List unavailable");
  expect(within(screen.getByRole("navigation", { name: "Available projects" })).getByRole("link", { name: "First project" })).toBeInTheDocument();
  nextFailure = false; await actor.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByText("List unavailable")).not.toBeInTheDocument());
  expect(within(screen.getByRole("navigation", { name: "Available projects" })).getAllByRole("link", { name: "Second project" })).toHaveLength(1);
});

it("renders read-only or archived details while retaining reading links and no audit request without capability", async () => {
  resource = { ...initial, archived_at: "2026-10-19", capabilities: { edit: false, archive: false } };
  mount(); await screen.findByText("Archived project — read only.");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument(); expect(card().getByRole("link", { name: "Workflow" })).toBeInTheDocument(); expect(card().getByRole("link", { name: "Members" })).toBeInTheDocument();
  expect(screen.queryByText("Change history")).not.toBeInTheDocument(); expect(auditCount).toBe(0);
});

it("allows editing independently of archive capability", async () => {
  resource = { ...initial, capabilities: { edit: true, archive: false } }; mount(); await screen.findByLabelText("Name");
  expect(screen.queryByRole("button", { name: "Archive project" })).not.toBeInTheDocument(); expect(screen.queryByText("Project details are read-only.")).not.toBeInTheDocument();
});

it.each([403, 404])("handles denied project detail %s with retry", async status => {
  detailFailure = status; const { actor } = mount(); await screen.findByRole("alert"); expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  detailFailure = 0; await actor.click(screen.getByRole("button", { name: "Retry" })); await screen.findByLabelText("Name");
});

it("creates on a separate route with paginated manager selection and never requests project new", async () => {
  const { actor, router, fetchMock } = mount(); await screen.findByLabelText("Name");
  await actor.click(screen.getByRole("link", { name: "Create project" })); await screen.findByText("Creating in", { exact: false });
  await actor.type(screen.getByLabelText("Name"), "Created project"); await actor.type(screen.getByLabelText("Description"), "Description");
  await actor.click(await screen.findByRole("checkbox", { name: "First Candidate" })); await actor.click(screen.getByRole("button", { name: "More candidates" })); await actor.click(await screen.findByRole("checkbox", { name: "Second Candidate" }));
  createFailure = 403; await actor.click(screen.getByRole("button", { name: "Create project" })); await screen.findByRole("alert"); expect(screen.getByLabelText("Name")).toHaveValue("Created project");
  createFailure = 0; await actor.click(screen.getByRole("button", { name: "Create project" })); await screen.findByRole("heading", { name: "Created project" });
  expect(router.state.location.pathname).toBe("/management/projects/created");
  expect(fetchMock).toHaveBeenCalledWith("/api/projects", expect.objectContaining({ method: "POST", body: JSON.stringify({ organization_id: "one", name: "Created project", description: "Description", manager_ids: ["m1", "m2"] }) }));
  expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/projects/new"))).toBe(false);
});

it("confirms dirty creation cancellation and organization change clears manager selection", async () => {
  const { actor, router, fetchMock } = mount("/management/projects/new?organization=one"); await screen.findByLabelText("Name");
  await actor.click(await screen.findByRole("checkbox", { name: "First Candidate" }));
  await actor.click(screen.getByRole("link", { name: "Cancel" })); await actor.click(screen.getByRole("button", { name: "Stay on page" }));
  expect(screen.getByRole("checkbox", { name: "First Candidate" })).toBeChecked();
  await actor.selectOptions(screen.getByLabelText("Organization"), "two"); await actor.click(screen.getByRole("button", { name: "Discard changes" }));
  await screen.findByText("Second organization", { selector: "strong" }); expect(await screen.findByRole("checkbox", { name: "First Candidate" })).not.toBeChecked();
  await actor.click(screen.getByRole("link", { name: "Cancel" })); expect(router.state.location.search).toBe("?organization=two");
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(0);
});

it.each([0, 403, 404])("enforces creation capability/direct URL denial (%s)", async status => {
  createAllowed = false; orgFailure = status; const { fetchMock } = mount("/management/projects/new?organization=one"); await screen.findByRole("alert");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument(); expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/projects/new"))).toBe(false);
});

it("confirms archive consequences, supports cancellation, retains failed object and blocks duplicate POST", async () => {
  const { actor, router, fetchMock } = mount(); await screen.findByLabelText("Name");
  await actor.click(screen.getByRole("button", { name: "Archive project" }));
  let dialog = screen.getByRole("dialog"); expect(dialog).toHaveTextContent("First project"); expect(dialog).toHaveTextContent("all its tasks"); expect(dialog).toHaveTextContent("Memberships move to the archived state");
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
  await actor.tab({ shift: true }); expect(within(dialog).getByRole("button", { name: "Archive project" })).toHaveFocus();
  fireEvent(dialog, new Event("cancel", { cancelable: true })); expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(screen.getByRole("button", { name: "Archive project" })).toHaveFocus();
  await actor.click(screen.getByRole("button", { name: "Archive project" })); archiveFailure = 409;
  await actor.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive project" })); await screen.findByText("Archive denied");
  let resolve!: (response: Response) => void; archiveWait = new Promise(r => { resolve = r; }); dialog = screen.getByRole("dialog");
  await actor.dblClick(within(dialog).getByRole("button", { name: "Archive project" })); expect(within(dialog).getByRole("button", { name: "Archive project" })).toBeDisabled();
  fireEvent(dialog, new Event("cancel", { cancelable: true })); expect(dialog).toBeInTheDocument();
  empty = true; await act(async () => resolve(await jsonResponse({ ...resource, archived_at: "2026-10-19" })));
  await screen.findByText("Project archived."); expect(router.state.location.pathname).toBe("/management/projects"); expect(router.state.location.search).toBe("?organization=one");
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/archive"))).toHaveLength(2);
});

it("keeps catalog retry and empty states separate from selected details", async () => {
  listFailure = true; const { actor } = mount(); await screen.findByLabelText("Name"); await screen.findByText("List unavailable");
  listFailure = false; empty = true; await actor.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByText("List unavailable")).not.toBeInTheDocument());
  expect(screen.getByLabelText("Name")).toHaveValue("First project");
  await actor.selectOptions(screen.getByLabelText("Organization"), "one");
  await screen.findByText("No projects yet.");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
});

it("disables pending creation and sends exactly one request", async () => {
  let resolve!: (response: Response) => void; createWait = new Promise(r => { resolve = r; });
  const { actor, fetchMock } = mount("/management/projects/new?organization=one"); await screen.findByLabelText("Name");
  await actor.type(screen.getByLabelText("Name"), "New project"); await actor.dblClick(screen.getByRole("button", { name: "Create project" }));
  expect(screen.getByRole("button", { name: "Creating project…" })).toBeDisabled(); expect(screen.getByLabelText("Name")).toBeDisabled(); expect(screen.getByRole("checkbox", { name: "First Candidate" })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(1);
  resource = { ...initial, name: "New project", id: "created" }; await act(async () => resolve(await jsonResponse(resource, 201)));
  await screen.findByRole("heading", { name: "New project" });
});

it("returns from pristine creation to the originating project", async () => {
  const { actor, router } = mount(); await screen.findByLabelText("Name"); await actor.click(screen.getByRole("link", { name: "Create project" })); await screen.findByText("Creating in", { exact: false });
  await actor.click(screen.getByRole("link", { name: "Cancel" })); await screen.findByLabelText("Name"); expect(router.state.location.pathname).toBe("/management/projects/p");
});

it("does not redirect a different project after a late archive response", async () => {
  let resolve!: (response: Response) => void; archiveWait = new Promise(r => { resolve = r; });
  const { actor, router } = mount(); await screen.findByLabelText("Name");
  await actor.click(screen.getByRole("button", { name: "Archive project" })); await actor.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Archive project" }));
  await act(async () => { await router.navigate("/management/projects/other"); }); await screen.findByRole("heading", { name: "Other project" });
  await act(async () => resolve(await jsonResponse({ ...initial, archived_at: "2026-10-19" })));
  expect(router.state.location.pathname).toBe("/management/projects/other"); expect(screen.queryByText("Project archived.")).not.toBeInTheDocument();
});

it("does not unmount a dirty draft when a background detail refresh temporarily fails", async () => {
  const { actor, client } = mount(); await screen.findByLabelText("Name"); await actor.type(screen.getByLabelText("Description"), " draft");
  detailFailure = 503;
  await act(async () => { await client.invalidateQueries({ queryKey: ["project", "p"] }); });
  await screen.findByText("Detail unavailable"); expect(screen.getByLabelText("Description")).toHaveValue("Original description draft");
  detailFailure = 0; await actor.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByText("Detail unavailable")).not.toBeInTheDocument());
  expect(screen.getByLabelText("Description")).toHaveValue("Original description draft");
});

it("shows audit loading and empty states only inside expanded history", async () => {
  let resolve!: (response: Response) => void; auditWait = new Promise(r => { resolve = r; });
  const { actor } = mount(); await screen.findByLabelText("Name"); expect(screen.queryByText("Loading audit...")).not.toBeInTheDocument();
  await actor.click(screen.getByText("Change history")); expect(await screen.findByText("Loading audit...")).toHaveAttribute("role", "status");
  await act(async () => resolve(await jsonResponse({ ...page([]), page_size: 20 })));
  await screen.findByText("No audit entries.");
  expect(screen.getByRole("button", { name: "Next audit page" })).toBeDisabled();
});
