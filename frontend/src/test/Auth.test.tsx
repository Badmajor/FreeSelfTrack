import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { App } from "../App";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("authentication form", () => {
  it("registers an account and signs in", async () => {
    const registeredUser = {
      id: "user-1",
      email: "new@example.com",
      is_active: true,
      profile: { user_id: "user-1", first_name: "Ada", last_name: "Lovelace" },
    };
    const fetchMock = vi.fn(
      (input: string | URL | Request, options?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/auth/refresh")) return jsonResponse({ detail: "Authentication required" }, 401);
        if (url.endsWith("/auth/register")) return jsonResponse({ message: "Check your email" }, 202);
        if (url.endsWith("/auth/login"))
          return jsonResponse({
            access_token: "token",
            token_type: "bearer",
            user: registeredUser,
          });
        if (url.endsWith("/organizations")) return jsonResponse([]);
        if (url.includes("/notifications/unread-count"))
          return jsonResponse({ count: 0 });
        return jsonResponse([], options?.method === "POST" ? 201 : 200);
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderWithQueryClient(<App />);
    await user.click(await screen.findByRole("tab", { name: "Register" }));
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "a long test passphrase");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Check your email",
    );
    await user.type(screen.getByLabelText("Password"), "a long test passphrase");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    expect(
      await screen.findByRole("heading", { name: "Organizations" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/auth/login",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          email: "new@example.com",
          password: "a long test passphrase",
        }),
      }),
    );
  });
});

it("confirms email only after an explicit password submission and clears the fragment", async () => {
  window.history.replaceState(null, "", "/#verify=test-confirmation-token");
  const fetchMock = vi.fn(() => jsonResponse({ message: "Confirmation processed" }));
  vi.stubGlobal("fetch", fetchMock);
  const user = userEvent.setup();
  renderWithQueryClient(<App />);
  expect(screen.getByRole("heading", { name: "Confirm your email" })).toBeInTheDocument();
  expect(window.location.hash).toBe("");
  expect(fetchMock).not.toHaveBeenCalled();
  await user.type(screen.getByLabelText("Registration password"), "a long test passphrase");
  await user.click(screen.getByRole("button", { name: "Confirm email" }));
  expect(await screen.findByRole("status")).toHaveTextContent("Confirmation processed");
  expect(fetchMock).toHaveBeenCalledWith("/api/auth/verify-email", expect.objectContaining({
    method: "POST", body: JSON.stringify({token: "test-confirmation-token", password: "a long test passphrase"}),
  }));
  expect(localStorage.getItem("freeselftrack.access_token")).toBeNull();
  await user.click(screen.getByRole("button", { name: "Continue to sign in" }));
  expect(screen.getByRole("heading", { name: "Welcome back" })).toBeInTheDocument();
});

it("shows expired confirmation errors and allows requesting a new registration", async () => {
  window.history.replaceState(null, "", "/#verify=expired-token");
  vi.stubGlobal("fetch", vi.fn(() => jsonResponse({ detail: "Invalid or expired confirmation" }, 400)));
  const user = userEvent.setup();
  renderWithQueryClient(<App />);
  await user.type(screen.getByLabelText("Registration password"), "a long test passphrase");
  await user.click(screen.getByRole("button", { name: "Confirm email" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("register again");
  await user.click(screen.getByRole("button", { name: "Back to sign in" }));
  await user.click(screen.getByRole("tab", { name: "Register" }));
  expect(screen.getByRole("heading", { name: "Create your account" })).toBeInTheDocument();
});
