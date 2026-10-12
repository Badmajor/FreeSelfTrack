import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../App";
import { clearSession } from "../api";
import { EmailChangeConfirmation } from "../EmailChangeConfirmation";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => {
  cleanup(); clearSession(); vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
  localStorage.clear(); sessionStorage.clear();
});

it("removes the email token from URL and requires login and explicit confirmation", async () => {
  const token = "email-change-test-secret";
  window.history.replaceState(null, "", `/#email-change=${token}`);
  const fetchMock = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/auth/login")) return jsonResponse({ access_token: "access", user: { id: "owner", email: "old@example.com", is_active: true } });
    if (url.endsWith("/email-change/confirm")) return jsonResponse({ detail: "Invalid or expired email confirmation" }, 422);
    return jsonResponse({ detail: "Authentication required" }, 401);
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<App />);
  expect(await screen.findByText(/Sign in to the account that requested/)).toBeInTheDocument();
  expect(window.location.hash).toBe("");
  expect(JSON.stringify(fetchMock.mock.calls)).not.toContain(token);
  const actor = userEvent.setup();
  await actor.type(screen.getByLabelText("Email"), "old@example.com");
  await actor.type(screen.getByLabelText("Password"), "password");
  await actor.click(screen.getByRole("button", { name: "Sign in" }));
  expect(await screen.findByRole("heading", { name: "Confirm email change" })).toBeInTheDocument();
  expect(JSON.stringify(fetchMock.mock.calls)).not.toContain(token);
  await actor.click(screen.getByRole("button", { name: "Confirm new email" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Invalid or expired email confirmation");
  expect(fetchMock).toHaveBeenLastCalledWith(expect.stringContaining("/users/me/email-change/confirm"), expect.objectContaining({ method: "POST", body: JSON.stringify({ token }) }));
  expect(JSON.stringify(localStorage)).not.toContain(token);
  expect(JSON.stringify(sessionStorage)).not.toContain(token);
  expect(screen.queryByText(token)).not.toBeInTheDocument();
});

it("confirms only once while pending and distinguishes cancel from success", async () => {
  let finish: (response: Response) => void = () => {};
  const fetchMock = vi.fn(() => new Promise<Response>(resolve => { finish = resolve; }));
  vi.stubGlobal("fetch", fetchMock);
  const onDone = vi.fn(), onClose = vi.fn();
  renderWithQueryClient(<EmailChangeConfirmation token="secret" email="old@example.com" onDone={onDone} onClose={onClose} onSignOut={vi.fn()} />);
  const actor = userEvent.setup();
  await actor.click(screen.getByRole("button", { name: "Confirm new email" }));
  expect(screen.getByRole("button", { name: "Confirm new email" })).toBeDisabled();
  finish(new Response(null, { status: 204 }));
  await screen.findByRole("button", { name: "Close confirmation" });
  await actor.click(screen.getByRole("button", { name: "Close confirmation" }));
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(onDone).toHaveBeenCalledTimes(1);
  expect(onClose).toHaveBeenCalledTimes(1);
});
