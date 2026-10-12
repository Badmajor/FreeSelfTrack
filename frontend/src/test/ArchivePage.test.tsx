import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { ArchivePage } from "../ArchivePage";
import { createTestQueryClient, jsonResponse } from "./test-utils";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

it("paginates archive and explains membership revocation before restoration", async () => {
  let restored = false;
  const fetch = vi.fn((input: string | URL | Request, options?: RequestInit) => {
    const url = String(input);
    if (url.endsWith("/restore")) { restored = true; return jsonResponse({ id: "org" }); }
    if (options?.method) throw new Error("Unexpected mutation");
    return jsonResponse({ items: restored ? [] : [{ id: "org", name: "Old organization", capabilities: { restore: true } }], next_cursor: null });
  });
  vi.stubGlobal("fetch", fetch);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<MemoryRouter><QueryClientProvider client={createTestQueryClient()}><ArchivePage /></QueryClientProvider></MemoryRouter>);
  expect(await screen.findByRole("link", { name: "Old organization" })).toHaveAttribute("href", "/management/organizations/org");
  await userEvent.click(screen.getByRole("button", { name: "Restore" }));
  expect(confirm).toHaveBeenCalledWith(expect.stringContaining("memberships will be revoked"));
  expect(await screen.findByText("No archived objects.")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/organizations/org/restore", expect.objectContaining({ method: "POST" }));
});

it("keeps archive visible on parent-state error and hides unauthorized restore", async () => {
  vi.stubGlobal("fetch", vi.fn((input: string | URL | Request) => String(input).endsWith("/restore")
    ? jsonResponse({ detail: "Restore the organization first" }, 409)
    : jsonResponse({ items: [{ id: "p", name: "Archived project", capabilities: { restore: true } }, { id: "p2", name: "Read only", capabilities: { restore: false } }], next_cursor: null })));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<MemoryRouter initialEntries={["/archive?organization=org"]}><QueryClientProvider client={createTestQueryClient()}><ArchivePage /></QueryClientProvider></MemoryRouter>);
  await screen.findByText("Archived project");
  expect(screen.getAllByRole("button", { name: "Restore" })).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "Restore" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Restore the organization first");
  expect(screen.getByText("Archived project")).toBeInTheDocument();
});

it("loads the next archive page without mixing scopes", async () => {
  const fetch = vi.fn((input: string | URL | Request) => {
    const next = String(input).includes("cursor=next-page");
    return jsonResponse({ items: [{ id: next ? "two" : "one", name: next ? "Second archived organization" : "First archived organization" }], next_cursor: next ? null : "next-page" });
  });
  vi.stubGlobal("fetch", fetch);
  render(<MemoryRouter><QueryClientProvider client={createTestQueryClient()}><ArchivePage /></QueryClientProvider></MemoryRouter>);
  await userEvent.click(await screen.findByRole("button", { name: "Load more" }));
  expect(await screen.findByText("Second archived organization")).toBeInTheDocument();
  expect(screen.getByText("First archived organization")).toBeInTheDocument();
  expect(fetch).toHaveBeenCalledWith("/api/organizations?state=archived&limit=50&cursor=next-page", expect.anything());
});
