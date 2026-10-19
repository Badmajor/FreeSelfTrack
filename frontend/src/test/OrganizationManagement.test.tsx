import { transferableAbortController } from "node:util";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { AuthenticatedApp } from "../WorkspaceApp";
import { type Organization } from "../api";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const admin = { id: "admin", email: "admin@example.com", is_active: true, is_system_admin: true };
const org: Organization = { id: "one", name: "First organization", description: "Original description", archived_at: null,
  capabilities: { edit: true, archive: true, manage_members: true, view_audit: true } };
const second = { ...org, id: "two", name: "Second organization" };
const page = (items: unknown[], next_cursor: string | null = null) => ({ items, next_cursor });
let resource = { ...org };
let empty = false;
let failure = 0;
let detailWait: Promise<Response> | undefined;
let patchFailure = 0;
let archiveFailure = 0;
let auditFailure = false;
let patchWait: Promise<Response> | undefined;
let createWait: Promise<Response> | undefined;
let archiveWait: Promise<Response> | undefined;
let createFailure = false;
let auditRequests = 0;

function mount(path = "/management/organizations/one", user = admin) {
  const fetchMock = vi.fn((input: string | URL | Request, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    if (url.includes("unread-count")) return jsonResponse({ count: 0 });
    if (url.endsWith("/projects") || url.includes("/members")) return jsonResponse(page([]));
    if (url.includes("/audit")) {
      auditRequests++;
      if (auditFailure) return jsonResponse({ detail: "Audit unavailable" }, 503);
      return jsonResponse({ ...page([], url.includes("cursor") ? null : "next"), page_size: 20 });
    }
    if (url.endsWith("/archive")) {
      if (archiveWait) return archiveWait;
      if (archiveFailure) return jsonResponse({ detail: "Archive denied" }, archiveFailure);
      empty = true; return jsonResponse({ ...resource, archived_at: "2026-10-14" });
    }
    if (init?.method === "PATCH") {
      if (patchWait) return patchWait;
      if (patchFailure) return jsonResponse({ detail: "Save denied" }, patchFailure);
      resource = { ...resource, ...JSON.parse(String(init.body)) }; return jsonResponse(resource);
    }
    if (init?.method === "POST") {
      if (createWait) return createWait;
      if (createFailure) return jsonResponse({ detail: "Creation failed" }, 503);
      resource = { ...resource, ...JSON.parse(String(init.body)) }; empty = false; return jsonResponse(resource, 201);
    }
    if (url.endsWith("/organizations/one")) return detailWait ?? (failure ? jsonResponse({ detail: "Detail unavailable" }, failure) : jsonResponse(resource));
    if (url.endsWith("/organizations/two")) return jsonResponse(second);
    if (url.includes("/organizations")) return jsonResponse(page(empty ? [] : url.includes("cursor") ? [second] : [resource], empty || url.includes("cursor") ? null : "next"));
    return jsonResponse(page([]));
  });
  vi.stubGlobal("fetch", fetchMock);
  const client = createTestQueryClient();
  const onSignOut = vi.fn();
  const router = createMemoryRouter([{ path: "*", element: <AuthenticatedApp user={user} onSignOut={onSignOut} onUserSaved={vi.fn()} /> }], { initialEntries: [path] });
  render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
  return { actor: userEvent.setup(), client, router, fetchMock, onSignOut };
}

// Keep the controller compatible with Node’s Request used by the data router.
beforeEach(() => {
  vi.stubGlobal("AbortController", function () { return transferableAbortController(); });
});

afterEach(() => {
  cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); localStorage.clear();
  resource = { ...org }; empty = false; failure = 0; patchFailure = 0; archiveFailure = 0; auditFailure = false;
  detailWait = undefined; patchWait = undefined; createWait = undefined; archiveWait = undefined; createFailure = false; auditRequests = 0;
});

it("separates creation from an empty directory and opens the created card and sidebar", async () => {
  empty = true;
  const { actor, router, fetchMock } = mount("/management/organizations");
  expect(await screen.findByText(/No organizations yet/)).toBeInTheDocument();
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  await actor.click(screen.getByRole("link", { name: "Create organization" }));
  expect(router.state.location.pathname).toBe("/management/organizations/new");
  expect(screen.queryByRole("navigation", { name: "Available organizations" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create organization" })).toBeDisabled();
  await actor.type(screen.getByLabelText("Name"), "New team");
  await actor.type(screen.getByLabelText("Description"), "New details");
  await actor.click(screen.getByRole("button", { name: "Create organization" }));
  expect(await screen.findByRole("heading", { name: "New team" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "New team" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: /New team/ })).toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/organizations/new"))).toBe(false);
});

it("denies direct creation to a non-SA without requests or fields", async () => {
  const { fetchMock } = mount("/management/organizations/new", { ...admin, is_system_admin: false });
  expect(await screen.findByRole("alert")).toHaveTextContent("system administrator");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  expect(fetchMock.mock.calls.some(([, init]) => init?.method === "POST")).toBe(false);
});

it("preserves failed creation input and prevents duplicate requests while pending", async () => {
  createFailure = true;
  const { actor, fetchMock } = mount("/management/organizations/new");
  await actor.type(screen.getByLabelText("Name"), "New organization");
  await actor.click(screen.getByRole("button", { name: "Create organization" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Creation failed");
  expect(screen.getByLabelText("Name")).toHaveValue("New organization");
  createWait = new Promise(() => {});
  await actor.dblClick(screen.getByRole("button", { name: "Create organization" }));
  expect(screen.getByRole("button", { name: "Creating organization..." })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "POST")).toHaveLength(2);
});

it("saves only valid changes, updates all names and cancels without a mutation", async () => {
  const { actor, fetchMock } = mount();
  const input = await screen.findByLabelText("Name");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await actor.clear(input); await actor.type(input, "   ");
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  await actor.clear(input); await actor.type(input, "Renamed team");
  await actor.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByText("Changes saved.")).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Renamed team" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Renamed team" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("button", { name: /Renamed team/ })).toBeInTheDocument();
  await actor.type(input, " draft");
  await actor.click(screen.getByRole("button", { name: "Cancel changes" }));
  expect(input).toHaveValue("Renamed team");
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(1);
  await actor.click(screen.getByRole("link", { name: "Create organization" }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

it("preserves drafts on refetch and stale permission errors, and prevents duplicate saves", async () => {
  patchFailure = 403;
  const { actor, client, fetchMock } = mount();
  const input = await screen.findByLabelText("Name");
  await actor.type(input, " draft");
  resource = { ...org, name: "Background update" };
  await act(() => client.invalidateQueries({ queryKey: ["organization", "one"] }));
  expect(input).toHaveValue("First organization draft");
  await actor.click(screen.getByRole("button", { name: "Save changes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Save denied");
  expect(input).toHaveValue("First organization draft");
  patchWait = new Promise(() => {});
  await actor.dblClick(screen.getByRole("button", { name: "Save changes" }));
  expect(screen.getByRole("button", { name: "Saving changes..." })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([, init]) => init?.method === "PATCH")).toHaveLength(2);
});

it("warns on organization, creation, member and history navigation, and before unload", async () => {
  const { actor, router } = mount();
  await screen.findByLabelText("Name");
  await actor.click(screen.getByRole("button", { name: "Load more organizations" }));
  await actor.click(await screen.findByRole("link", { name: "Second organization" }));
  await actor.type(await screen.findByLabelText("Name"), " draft");
  for (const name of ["First organization", "Create organization", "Manage members"]) {
    await actor.click(screen.getByRole("link", { name }));
    expect(screen.getByRole("dialog")).toHaveAccessibleName("Discard unsaved changes?");
    expect(screen.getByRole("button", { name: "Stay on page" })).toHaveFocus();
    await actor.tab();
    expect(screen.getByRole("button", { name: "Discard changes" })).toHaveFocus();
    await actor.tab();
    expect(screen.getByRole("button", { name: "Stay on page" })).toHaveFocus();
    await actor.click(screen.getByRole("button", { name: "Stay on page" }));
    expect(router.state.location.pathname).toBe("/management/organizations/two");
  }
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event); expect(event.defaultPrevented).toBe(true);
  await act(() => router.navigate(-1));
  await actor.click(screen.getByRole("button", { name: "Stay on page" }));
  await act(() => router.navigate(-1));
  await actor.click(screen.getByRole("button", { name: "Discard changes" }));
  await waitFor(() => expect(router.state.location.pathname).toBe("/management/organizations/one"));
  await act(() => router.navigate(1));
  expect(await screen.findByLabelText("Name")).toHaveValue("Second organization");
  const cleanEvent = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(cleanEvent); expect(cleanEvent.defaultPrevented).toBe(false);
});

it("loads audit only on disclosure, preserves drafts, supports retry/pages/refresh and resets on switch", async () => {
  const { actor } = mount();
  await actor.type(await screen.findByLabelText("Name"), " draft");
  expect(auditRequests).toBe(0);
  auditFailure = true;
  await actor.click(screen.getByText("Administrative audit"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Audit unavailable");
  auditFailure = false;
  await actor.click(screen.getByRole("button", { name: "Retry audit" }));
  expect(await screen.findByText("No audit entries.")).toBeInTheDocument();
  expect(screen.getByLabelText("Name")).toHaveValue("First organization draft");
  await actor.click(screen.getByRole("button", { name: "Next audit page" }));
  expect(await screen.findByText(/Page 2/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Refresh audit" })).toBeEnabled());
  await actor.click(screen.getByRole("button", { name: "Refresh audit" }));
  expect(await screen.findByText(/Page 1/)).toBeInTheDocument();
  await actor.click(screen.getByRole("button", { name: "Cancel changes" }));
  await actor.click(screen.getByRole("button", { name: "Load more organizations" }));
  await actor.click(await screen.findByRole("link", { name: "Second organization" }));
  expect(await screen.findByLabelText("Name")).toHaveValue("Second organization");
  expect(screen.queryByRole("button", { name: "Refresh audit" })).not.toBeInTheDocument();
});

it("keeps member reading for readers and archived cards without forbidden controls or audit requests", async () => {
  resource = { ...org, archived_at: "2026-10-14", description: null, capabilities: {} };
  mount(undefined, { ...admin, is_system_admin: false });
  expect(await screen.findByText("Archived organization — read only.")).toBeInTheDocument();
  expect(screen.getByText("No description provided.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "View members" })).toBeInTheDocument();
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive organization" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Create organization" })).not.toBeInTheDocument();
  expect(auditRequests).toBe(0);
});

it("allows local manager edits and member management without implying archive permission", async () => {
  resource = { ...org, capabilities: { edit: true, manage_members: true, view_audit: true, archive: false } };
  mount(undefined, { ...admin, is_system_admin: false });
  expect(await screen.findByLabelText("Name")).toBeEnabled();
  expect(screen.getByRole("link", { name: "Manage members" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Archive organization" })).not.toBeInTheDocument();
  expect(screen.queryByText(/administration requires/)).not.toBeInTheDocument();
});

it.each([403, 404, 503])("distinguishes detail failure %s from unavailable resources", async status => {
  failure = status;
  const { actor } = mount();
  expect(await screen.findByRole("alert")).toHaveTextContent(status === 503 ? "Detail unavailable" : "Organization not found or unavailable");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  if (status === 503) {
    failure = 0; await actor.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByLabelText("Name")).toBeInTheDocument();
  }
});

it("opens a selected organization outside the first page and retains paginated links", async () => {
  const { actor } = mount("/management/organizations/two");
  expect(await screen.findByLabelText("Name")).toHaveValue("Second organization");
  await actor.click(screen.getByRole("button", { name: "Load more organizations" }));
  expect(await screen.findByRole("link", { name: "Second organization" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("link", { name: "First organization" })).toBeInTheDocument();
});

it("confirms archive consequences, cancels safely, retains failed cards and navigates after success", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const { actor, fetchMock, router } = mount();
  const button = await screen.findByRole("button", { name: "Archive organization" });
  await actor.click(button);
  expect(confirm).toHaveBeenCalledWith(expect.stringMatching(/First organization.*projects and tasks.*Memberships.*Restoring/));
  expect(fetchMock.mock.calls.some(([url]) => String(url).endsWith("/archive"))).toBe(false);
  expect(button).toHaveFocus();
  confirm.mockReturnValue(true); archiveFailure = 409;
  await actor.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Archive denied");
  expect(screen.getByLabelText("Name")).toHaveValue(org.name);
  archiveFailure = 0;
  await actor.click(button);
  expect(await screen.findByText("Organization archived.")).toBeInTheDocument();
  expect(router.state.location.pathname).toBe("/management/organizations");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
});

it("disables duplicate archive and save while archiving", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
  archiveWait = new Promise(() => {});
  const { actor, fetchMock } = mount();
  await actor.type(await screen.findByLabelText("Name"), " draft");
  await actor.dblClick(screen.getByRole("button", { name: "Archive organization" }));
  expect(screen.getByRole("button", { name: "Archiving organization..." })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Save changes" })).toBeDisabled();
  expect(fetchMock.mock.calls.filter(([url]) => String(url).endsWith("/archive"))).toHaveLength(1);
});

it("shows loading and retry for catalog failures without blocking direct card reading", async () => {
  const { client } = mount();
  await screen.findByLabelText("Name");
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "Catalog offline" }, 503)));
  await act(() => client.invalidateQueries({ queryKey: ["organizations", "pages"] }));
  expect(await within(screen.getByRole("navigation", { name: "Available organizations" })).findByRole("alert")).toHaveTextContent("Catalog offline");
  expect(screen.getByLabelText("Name")).toHaveValue(org.name);
  fireEvent.click(within(screen.getByRole("navigation", { name: "Available organizations" })).getByRole("button", { name: "Retry" }));
});


it("warns before sign-out only while changes are unsaved", async () => {
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  const { actor, onSignOut } = mount();
  await actor.type(await screen.findByLabelText("Name"), " draft");
  await actor.click(screen.getByRole("button", { name: "Sign out" }));
  expect(confirm).toHaveBeenCalledWith("Discard unsaved changes and sign out?");
  expect(onSignOut).not.toHaveBeenCalled();
  await actor.click(screen.getByRole("button", { name: "Save changes" }));
  await screen.findByText("Changes saved.");
  confirm.mockClear();
  await actor.click(screen.getByRole("button", { name: "Sign out" }));
  expect(onSignOut).toHaveBeenCalledOnce();
  expect(confirm).not.toHaveBeenCalled();
});


it("shows detail loading without stale catalog controls, then renders the response", async () => {
  let resolve!: (response: Response) => void;
  detailWait = new Promise(done => { resolve = done; });
  mount();
  expect(await screen.findByText("Loading organization...")).toHaveAttribute("role", "status");
  expect(screen.queryByLabelText("Name")).not.toBeInTheDocument();
  await act(async () => resolve(await jsonResponse(resource)));
  expect(await screen.findByLabelText("Name")).toHaveValue(org.name);
});


it("keeps the empty-state message and creation visible with a collapsed mobile selector", async () => {
  empty = true;
  vi.stubGlobal("matchMedia", () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }));
  mount("/management/organizations");
  expect(await screen.findByText(/No organizations yet/)).toBeVisible();
  expect(screen.getByRole("link", { name: "Create organization" })).toBeVisible();
  expect(screen.getByRole("navigation", { name: "Available organizations" })).not.toBeVisible();
});


it("keeps unsaved input when a background detail refresh fails temporarily", async () => {
  const { actor, client } = mount();
  await actor.type(await screen.findByLabelText("Name"), " draft");
  failure = 503;
  await act(() => client.invalidateQueries({ queryKey: ["organization", "one"] }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Detail unavailable");
  expect(screen.getByLabelText("Name")).toHaveValue("First organization draft");
  failure = 0;
  await actor.click(screen.getByRole("button", { name: "Retry" }));
  await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  expect(screen.getByLabelText("Name")).toHaveValue("First organization draft");
});
