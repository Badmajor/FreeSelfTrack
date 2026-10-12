import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { UserCardPage, EmailChangeForm } from "../UserCardPage";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => { cleanup(); vi.restoreAllMocks(); });
const user = { id: "visitor", email: "visitor@example.com", is_active: true };

it("shows inaccessible membership names without links and paginates", async () => {
  const fetchMock = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/users/target")) return jsonResponse({
      id: "target", first_name: "Other", last_name: "User", is_active: false,
      created_at: "2026-01-01T00:00:00Z", capabilities: {},
    });
    if (url.includes("organizations")) return jsonResponse({ items: [{ id: "hidden", name: "Hidden organization", role: "member", can_open: false }], next_cursor: null });
    if (url.includes("cursor=next")) return jsonResponse({ items: [{ id: "second", name: "Second project", role: "member", can_open: true, organization_name: "Visible organization" }], next_cursor: null });
    return jsonResponse({ items: [{ id: "secret", name: "Hidden project", role: "manager", can_open: false, organization_name: "Hidden organization" }], next_cursor: "next" });
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<Routes>
    <Route path="/" element={<Navigate to="/users/target" />} />
    <Route path="/users/:userId" element={<UserCardPage user={user} onSaved={vi.fn()} />} />
  </Routes>);
  expect(await screen.findByRole("heading", { name: "Other User" })).toBeInTheDocument();
  expect(await screen.findByText("Hidden project (No access)")).toBeInTheDocument();
  expect(screen.getByText("Hidden organization (No access)")).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Hidden project" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Save profile" })).not.toBeInTheDocument();
  expect(screen.queryByLabelText("New email")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Load more projects" }));
  expect(await screen.findByRole("link", { name: "Second project" })).toHaveAttribute("href", "/management/projects/second");
  expect(screen.getByText("Hidden project (No access)")).toBeInTheDocument();
});

it("saves an authorized profile and displays backend errors", async () => {
  let updated = false;
  const fetchMock = vi.fn((input: string | URL | Request, options?: RequestInit) => {
    const url = String(input);
    if (options?.method === "PATCH") {
      if (JSON.parse(String(options.body)).first_name === "Rejected") return jsonResponse({ detail: "System administrator required" }, 403);
      updated = true;
      return jsonResponse({ user_id: "target", first_name: "Updated", last_name: "User" });
    }
    if (url.endsWith("/users/target")) return jsonResponse({ id: "target", first_name: updated ? "Updated" : "Other", last_name: "User", is_active: true, created_at: "2026-01-01", capabilities: { edit_profile: true, change_email: true } });
    return jsonResponse({ items: [], next_cursor: null });
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<Routes>
    <Route path="/" element={<Navigate to="/users/target" />} />
    <Route path="/users/:userId" element={<UserCardPage user={user} onSaved={vi.fn()} />} />
  </Routes>);
  const actor = userEvent.setup();
  const first = await screen.findByLabelText("First name");
  await actor.clear(first); await actor.type(first, "Rejected");
  await actor.click(screen.getByRole("button", { name: "Save profile" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("System administrator required");
  await actor.clear(first); await actor.type(first, "Updated");
  await actor.click(screen.getByRole("button", { name: "Save profile" }));
  expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledWith(expect.stringContaining("/users/target/profile"), expect.objectContaining({ method: "PATCH", body: JSON.stringify({ first_name: "Updated", last_name: "User" }) }));
});

it.each([true, false])("changes email with self=%s using the appropriate API", async self => {
  const fetchMock = vi.fn().mockImplementationOnce(() => jsonResponse({ detail: "Email is already in use" }, 409))
    .mockImplementation(() => jsonResponse(self ? { message: "Check your new email address.", expires_at: "2026-10-12T20:00:00Z" } : { id: "target" }));
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<EmailChangeForm targetId="target" self={self} />);
  const actor = userEvent.setup();
  await actor.type(screen.getByLabelText("New email"), "new@example.com");
  const submit = screen.getByRole("button", { name: self ? "Send confirmation" : "Change email directly" });
  await actor.click(submit);
  expect(await screen.findByRole("alert")).toHaveTextContent("Email is already in use");
  await actor.click(submit);
  expect(await screen.findByRole("status")).toHaveTextContent(self ? "Previous links are cancelled" : "Email changed");
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining(self ? "/users/me/email-change" : "/users/target/email"), expect.objectContaining({ method: self ? "POST" : "PATCH", body: JSON.stringify({ email: "new@example.com" }) }));
});
