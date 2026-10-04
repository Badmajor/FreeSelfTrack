import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../App";
import { AccountSecurity } from "../AccountSecurity";
import {
  clearSession,
  getMyProfile,
  listOrganizations,
  login,
  logout,
  restoreSession,
} from "../api";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

const user = { id: "user-1", email: "user@example.com", is_active: true };
const auth = (token = "access-token") => ({
  access_token: token,
  token_type: "bearer",
  user,
});

afterEach(() => {
  cleanup();
  clearSession();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

it("restores a cookie session and removes legacy credentials from localStorage", async () => {
  localStorage.setItem("freeselftrack.access_token", "legacy-token");
  localStorage.setItem("freeselftrack.user", JSON.stringify(user));
  const fetchMock = vi.fn((input: string | URL | Request) => {
    if (String(input).endsWith("/auth/refresh")) return jsonResponse(auth());
    if (String(input).includes("unread-count"))
      return jsonResponse({ count: 0 });
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<App />);
  expect(screen.getByRole("status")).toHaveTextContent("Restoring session");
  expect(
    await screen.findByRole("heading", { name: "Organizations" }),
  ).toBeInTheDocument();
  expect(localStorage.getItem("freeselftrack.access_token")).toBeNull();
  expect(localStorage.getItem("freeselftrack.user")).toBeNull();
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/refresh",
    expect.objectContaining({
      credentials: "include",
      method: "POST",
      headers: expect.objectContaining({ "X-CSRF-Protection": "1" }),
    }),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/organizations",
    expect.objectContaining({
      headers: expect.objectContaining({
        Authorization: "Bearer access-token",
      }),
    }),
  );
});

it("shares one refresh for concurrent expired requests and retries with the new token", async () => {
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) return jsonResponse(auth("old"));
      if (url.endsWith("/auth/refresh")) return jsonResponse(auth("new"));
      const headers = options?.headers as Record<string, string>;
      return headers.Authorization === "Bearer new"
        ? jsonResponse([])
        : jsonResponse({ detail: "Authentication required" }, 401);
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  await login(user.email, "test password");
  await Promise.all([listOrganizations(), getMyProfile()]);
  expect(
    fetchMock.mock.calls.filter(([url]) =>
      String(url).endsWith("/auth/refresh"),
    ),
  ).toHaveLength(1);
  expect(localStorage.getItem("freeselftrack.access_token")).toBeNull();
});

it("rejects a revoked refresh and clears the authenticated UI", async () => {
  let revoked = false;
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh"))
        return revoked
          ? jsonResponse({ detail: "Authentication required" }, 401)
          : jsonResponse(auth());
      if (url.includes("unread-count")) return jsonResponse({ count: 0 });
      return revoked
        ? jsonResponse({ detail: "Authentication required" }, 401)
        : jsonResponse([]);
    }),
  );
  renderWithQueryClient(<App />);
  await screen.findByRole("heading", { name: "Organizations" });
  revoked = true;
  await expect(listOrganizations()).rejects.toThrow("Authentication required");
  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();
});

it("waits for logout success and shows a recoverable logout failure", async () => {
  let failed = true;
  const fetchMock = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/auth/refresh")) return jsonResponse(auth());
    if (url.endsWith("/auth/logout"))
      return failed
        ? jsonResponse({ detail: "Unavailable" }, 503)
        : Promise.resolve(new Response(null, { status: 204 }));
    if (url.includes("unread-count")) return jsonResponse({ count: 0 });
    return jsonResponse([]);
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<App />);
  const actor = userEvent.setup();
  await screen.findByRole("heading", { name: "Organizations" });
  await actor.click(screen.getByRole("button", { name: /Sign out/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Sign out failed");
  expect(
    screen.getByRole("heading", { name: "Organizations" }),
  ).toBeInTheDocument();
  failed = false;
  await actor.click(screen.getByRole("button", { name: /Sign out/i }));
  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();
});

it("does not resurrect an in-flight refresh after logout", async () => {
  let release!: (response: Response) => void;
  const pending = new Promise<Response>((resolve) => {
    release = resolve;
  });
  const fetchMock = vi.fn((input: string | URL | Request) =>
    String(input).endsWith("/auth/refresh")
      ? pending
      : Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal("fetch", fetchMock);
  const refreshing = restoreSession();
  const rejected = expect(refreshing).rejects.toThrow("Session changed");
  const leaving = logout();
  release(new Response(JSON.stringify(auth())));
  await rejected;
  await leaving;
  expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
    "/api/auth/refresh",
    "/api/auth/logout",
  ]);
});

it("shows a retry state when restoration fails due to the network", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockRejectedValue(new TypeError("Network error")),
  );
  renderWithQueryClient(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to restore",
  );
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();
  expect(screen.getByLabelText("Email")).toBeInTheDocument();
});

it("requests a reset using a neutral response", async () => {
  const fetchMock = vi.fn((input: string | URL | Request) =>
    String(input).endsWith("/auth/refresh")
      ? jsonResponse({ detail: "Authentication required" }, 401)
      : jsonResponse(
          {
            message:
              "If this account is active, a password reset link will be emailed.",
          },
          202,
        ),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<App />);
  const actor = userEvent.setup();
  await actor.click(
    await screen.findByRole("button", { name: "Forgot password?" }),
  );
  await actor.type(screen.getByLabelText("Email"), user.email);
  await actor.click(screen.getByRole("button", { name: "Send reset link" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "If this account is active",
  );
});

it("clears the reset fragment and submits the token only after an explicit password choice", async () => {
  window.history.replaceState(null, "", "/#reset=single-use-token");
  const fetchMock = vi.fn(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<App />);
  expect(window.location.hash).toBe("");
  expect(fetchMock).not.toHaveBeenCalled();
  const actor = userEvent.setup();
  await actor.type(
    screen.getByLabelText("New password"),
    "a sufficiently long new password",
  );
  await actor.click(screen.getByRole("button", { name: "Save new password" }));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Password changed",
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/password/reset",
    expect.objectContaining({
      body: JSON.stringify({
        token: "single-use-token",
        new_password: "a sufficiently long new password",
      }),
    }),
  );
});

it("shows ownership errors for deactivation and requires explicit confirmation", async () => {
  const fetchMock = vi.fn(() =>
    jsonResponse(
      {
        detail:
          "Transfer organization and project ownership before deactivation",
      },
      409,
    ),
  );
  vi.stubGlobal("fetch", fetchMock);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  renderWithQueryClient(<AccountSecurity />);
  const actor = userEvent.setup();
  await actor.type(
    screen.getByLabelText("Current password"),
    "my existing password",
  );
  await actor.click(screen.getByRole("button", { name: "Deactivate account" }));
  expect(fetchMock).not.toHaveBeenCalled();
  confirm.mockReturnValue(true);
  await actor.click(screen.getByRole("button", { name: "Deactivate account" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Transfer organization",
  );
});

it("submits current and new passwords and clears credentials on success", async () => {
  const fetchMock = vi.fn(() =>
    Promise.resolve(new Response(null, { status: 204 })),
  );
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(<AccountSecurity />);
  const actor = userEvent.setup();
  await actor.type(
    screen.getByLabelText("Current password"),
    "existing password",
  );
  await actor.type(
    screen.getByLabelText("New password"),
    "a sufficiently long new password",
  );
  await actor.click(screen.getByRole("button", { name: "Change password" }));
  await waitFor(() =>
    expect(screen.getByLabelText("Current password")).toHaveValue(""),
  );
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/auth/password/change",
    expect.objectContaining({
      body: JSON.stringify({
        current_password: "existing password",
        new_password: "a sufficiently long new password",
      }),
    }),
  );
});

it("refreshes an expired access token before changing a password, but preserves wrong-password errors", async () => {
  let refreshCount = 0;
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input);
      if (url.endsWith("/auth/login")) return jsonResponse(auth("old"));
      if (url.endsWith("/auth/refresh")) {
        refreshCount += 1;
        return jsonResponse(auth("new"));
      }
      const headers = options?.headers as Record<string, string>;
      return jsonResponse(
        {
          detail:
            headers.Authorization === "Bearer new"
              ? "Invalid email or password"
              : "Authentication required",
        },
        401,
      );
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  await login(user.email, "existing password");
  const { changePassword } = await import("../api");
  await expect(
    changePassword("wrong", "a sufficiently long new password"),
  ).rejects.toThrow("Invalid email or password");
  expect(refreshCount).toBe(1);
  await expect(
    changePassword("wrong", "a sufficiently long new password"),
  ).rejects.toThrow("Invalid email or password");
  expect(refreshCount).toBe(1);
});

it("explains rejected restoration while keeping sign-in available", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.endsWith("/auth/refresh"))
        return jsonResponse({ detail: "Invalid request origin" }, 403);
      if (url.endsWith("/auth/login")) return jsonResponse(auth());
      if (url.includes("unread-count")) return jsonResponse({ count: 0 });
      return jsonResponse([]);
    }),
  );
  renderWithQueryClient(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "configured application address",
  );
  const actor = userEvent.setup();
  await actor.type(screen.getByLabelText("Email"), user.email);
  await actor.type(screen.getByLabelText("Password"), "existing password");
  await actor.click(screen.getByRole("button", { name: "Sign in" }));
  expect(
    await screen.findByRole("heading", { name: "Organizations" }),
  ).toBeInTheDocument();
  expect(
    screen.queryByText(/Session restoration was rejected/),
  ).not.toBeInTheDocument();
});
