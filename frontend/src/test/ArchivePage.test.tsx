import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, useNavigate } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { login } from "../api";
import { ArchivePage } from "../ArchivePage";
import { createTestQueryClient, jsonResponse } from "./test-utils";

const item = { id: "org", name: "Old organization", capabilities: { restore: true } };
const page = (items = [item], next_cursor: string | null = null) => ({ items, next_cursor });
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });
function Navigation() {
  const navigate = useNavigate();
  return <><button onClick={() => navigate("/archive?organization=other")}>Other parent</button><button onClick={() => navigate(-1)}>Back</button><button onClick={() => navigate(1)}>Forward</button></>;
}
function setup(url = "/archive") {
  const client = createTestQueryClient();
  render(<MemoryRouter initialEntries={[url]}><QueryClientProvider client={client}><Navigation /><ArchivePage /></QueryClientProvider></MemoryRouter>);
  return client;
}
async function open(name = item.name) {
  await userEvent.click(await screen.findByRole("button", { name: `Restore ${name}` }));
  return screen.getByRole("dialog");
}

it("shows contextual links and requires named confirmation; Cancel/Escape restore focus without POST", async () => {
  const fetch = vi.fn(() => jsonResponse(page())); vi.stubGlobal("fetch", fetch); setup();
  expect(await screen.findByRole("link", { name: item.name })).toHaveAttribute("href", "/management/organizations/org");
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Archived organizations");
  expect(screen.getByRole("link", { name: "Archived projects of Old organization" })).toHaveAttribute("href", "/archive?organization=org");
  const dialog = await open();
  expect(dialog).toHaveAccessibleName("Restore organization?");
  expect(dialog).toHaveAccessibleDescription(expect.stringContaining("organization and all its projects will be revoked"));
  expect(within(dialog).getByText(/Old organization/)).toBeInTheDocument();
  expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
  await userEvent.tab({ shift: true }); expect(within(dialog).getByRole("button", { name: "Restore organization" })).toHaveFocus();
  await userEvent.tab(); expect(within(dialog).getByRole("button", { name: "Cancel" })).toHaveFocus();
  await userEvent.keyboard("{Escape}"); expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Restore Old organization" })).toHaveFocus();
  await open(); await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(fetch).toHaveBeenCalledTimes(1);
});

it("blocks duplicate submissions and pending dismissal, refreshes caches, announces success and focuses heading", async () => {
  let resolve!: (response: Response) => void; let restored = false;
  const fetch = vi.fn((input: string | URL | Request) => String(input).endsWith("/restore")
    ? new Promise<Response>(r => { resolve = r; }) : jsonResponse(page(restored ? [] : [item])));
  vi.stubGlobal("fetch", fetch); const client = setup(); client.setQueryDefaults(["organizations"], { gcTime: Infinity }); client.setQueryData(["organizations"], [item]);
  await open(); await userEvent.dblClick(screen.getByRole("button", { name: "Restore organization" }));
  expect(screen.getByRole("button", { name: "Restoring…" })).toBeDisabled();
  await userEvent.keyboard("{Escape}"); await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/restore"))).toHaveLength(1);
  restored = true; await act(async () => resolve(await jsonResponse(item)));
  expect(await screen.findByText("No archived organizations")).toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("“Old organization” restored.");
  await waitFor(() => expect(screen.getByRole("heading", { level: 1 })).toHaveFocus());
  expect(client.getQueryState(["organizations"])?.isInvalidated).toBe(true);
  expect(fetch).toHaveBeenCalledWith("/api/organizations/org/restore", expect.objectContaining({ method: "POST" }));
});

it.each([403, 404, 409])("keeps failed restore visible with retry and cancel (%s)", async status => {
  let fail = true;
  vi.stubGlobal("fetch", vi.fn((input: string | URL | Request) => String(input).endsWith("/restore")
    ? jsonResponse(fail ? { detail: "parent_archived" } : item, fail ? status : 200) : jsonResponse(page())));
  setup(); await open(); await userEvent.click(screen.getByRole("button", { name: "Restore organization" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(status === 403 ? "permission" : status === 404 ? "no longer available" : "parent");
  expect(screen.getByRole("link", { name: item.name })).toBeInTheDocument();
  expect(screen.getByRole("status")).toBeEmptyDOMElement();
  fail = false; await userEvent.click(screen.getByRole("button", { name: "Restore organization" }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

it("preserves first page on next-page failure and retries only its cursor", async () => {
  let fail = true;
  const fetch = vi.fn((input: string | URL | Request) => String(input).includes("cursor=next-page")
    ? fail ? jsonResponse({ detail: "Temporary failure" }, 503) : jsonResponse(page([{ ...item, id: "two", name: "Second" }]))
    : jsonResponse(page([item], "next-page")));
  vi.stubGlobal("fetch", fetch); setup();
  await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load more");
  expect(screen.getByRole("link", { name: item.name })).toBeInTheDocument();
  fail = false; await userEvent.click(screen.getByRole("button", { name: "Retry loading more" }));
  expect(await screen.findByRole("link", { name: "Second" })).toBeInTheDocument();
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  expect(fetch.mock.calls.filter(([url]) => !String(url).includes("cursor="))).toHaveLength(1);
});

it("handles initial loading, error/retry and read-only capabilities including missing ones", async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn().mockImplementationOnce(() => new Promise<Response>(r => { resolve = r; }))
    .mockImplementation(() => jsonResponse({ items: [{ id: "one", name: "X".repeat(200) }, { id: "two", name: "Read only", capabilities: { restore: false } }], next_cursor: null }));
  vi.stubGlobal("fetch", fetch); setup(); expect(screen.getByText("Loading archive…")).toHaveAttribute("role", "status");
  await act(async () => resolve(await jsonResponse({ detail: "Unavailable" }, 503)));
  await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
  await screen.findByText("Read only"); expect(screen.queryByRole("button", { name: /^Restore/ })).not.toBeInTheDocument();
});

it.each([ ["/archive?organization=org", "project", "Archived projects", "/management/projects/org"], ["/archive?project=p", "task", "Archived tasks", "/projects/p/kanban/tasks/org"] ])("preserves nested route %s and scope-specific restoration", async (url, scope, title, href) => {
  const fetch = vi.fn(() => jsonResponse(page())); vi.stubGlobal("fetch", fetch); setup(url);
  expect(await screen.findByRole("link", { name: item.name })).toHaveAttribute("href", href);
  expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(title);
  expect(screen.getByRole("link", { name: "Archived organizations" })).toHaveAttribute("href", "/archive");
  const dialog = await open();
  expect(dialog).toHaveAccessibleDescription(expect.stringContaining(scope === "task" ? "Only this task" : "Previous project memberships"));
  await userEvent.click(within(dialog).getByRole("button", { name: `Restore ${scope}` }));
  await waitFor(() => expect(fetch).toHaveBeenCalledWith(`/api/${scope}s/org/restore`, expect.objectContaining({ method: "POST" })));
});

it("isolates pages and late mutation results across parent changes and Back/Forward", async () => {
  let resolve!: (response: Response) => void;
  const fetch = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/restore")) return new Promise<Response>(r => { resolve = r; });
    return jsonResponse(page([{ ...item, name: url.includes("/other/") ? "Other project" : item.name }]));
  });
  vi.stubGlobal("fetch", fetch); setup("/archive?organization=org"); await open();
  await userEvent.click(screen.getByRole("button", { name: "Restore project" }));
  await userEvent.click(screen.getByRole("button", { name: "Other parent" }));
  await screen.findByRole("link", { name: "Other project" });
  await act(async () => resolve(await jsonResponse(item)));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(screen.getByRole("status")).toBeEmptyDOMElement();
  expect(screen.queryByRole("link", { name: item.name })).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Back" })); await screen.findByRole("link", { name: item.name });
  await userEvent.click(screen.getByRole("button", { name: "Forward" })); await screen.findByRole("link", { name: "Other project" });
  expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/restore"))).toHaveLength(1);
});

it("uses the existing session-ended flow when restore and refresh return 401", async () => {
  const ended = vi.fn(); window.addEventListener("freeselftrack:session-ended", ended);
  const fetch = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/auth/login")) return jsonResponse({ access_token: "synthetic", user: { id: "u" } });
    if (url.endsWith("/restore") || url.endsWith("/auth/refresh")) return jsonResponse({ detail: "Authentication required" }, 401);
    return jsonResponse(page());
  });
  vi.stubGlobal("fetch", fetch);
  try {
    await login("test@example.com", "synthetic"); setup(); await open();
    await userEvent.click(screen.getByRole("button", { name: "Restore organization" }));
    await waitFor(() => expect(ended).toHaveBeenCalledOnce());
    expect(screen.getByRole("status")).toBeEmptyDOMElement();
    expect(fetch.mock.calls.filter(([url]) => String(url).endsWith("/restore"))).toHaveLength(1);
  } finally { window.removeEventListener("freeselftrack:session-ended", ended); }
});
