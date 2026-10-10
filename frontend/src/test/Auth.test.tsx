import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "../App";
import { clearSession } from "../api";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => {
  cleanup();
  clearSession();
  vi.restoreAllMocks();
  window.history.replaceState(null, "", "/");
});

it.each(["verify", "reset"])(
  "disables old %s links and never submits their credentials",
  async (kind) => {
    window.history.replaceState(null, "", `/#${kind}=legacy-secret`);
    const fetchMock = vi.fn(() =>
      jsonResponse({ detail: "Authentication required" }, 401),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithQueryClient(<App />);
    expect(
      await screen.findByRole("heading", { name: "Welcome back" }),
    ).toBeInTheDocument();
    expect(window.location.hash).toBe("");
    expect(screen.getByRole("status")).toHaveTextContent("no longer supported");
    expect(
      screen.queryByRole("tab", { name: "Register" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("Forgot password?")).not.toBeInTheDocument();
    expect(JSON.stringify(fetchMock.mock.calls)).not.toContain("legacy-secret");
  },
);

it("requires a permanent password before any workspace requests and returns to login", async () => {
  const user = {
    id: "temporary",
    email: "temp@example.com",
    is_active: true,
    must_change_password: true,
  };
  const fetchMock = vi.fn((input: string | URL | Request) => {
    const url = String(input);
    if (url.endsWith("/auth/refresh"))
      return jsonResponse({ detail: "Authentication required" }, 401);
    if (url.endsWith("/auth/login"))
      return jsonResponse({ access_token: "token", user });
    if (url.endsWith("/auth/password/change"))
      return Promise.resolve(new Response(null, { status: 204 }));
    throw new Error(`Unexpected request ${url}`);
  });
  vi.stubGlobal("fetch", fetchMock);
  const actor = userEvent.setup();
  renderWithQueryClient(<App />);
  await actor.type(await screen.findByLabelText("Email"), user.email);
  await actor.type(screen.getByLabelText("Password"), "temporary password");
  await actor.click(screen.getByRole("button", { name: "Sign in" }));
  expect(
    await screen.findByRole("heading", { name: "Set a permanent password" }),
  ).toBeInTheDocument();
  expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  await actor.type(
    screen.getByLabelText("Current password"),
    "temporary password",
  );
  await actor.type(
    screen.getByLabelText("New password"),
    "a new permanent password",
  );
  await actor.click(screen.getByRole("button", { name: "Change password" }));
  expect(
    await screen.findByRole("heading", { name: "Welcome back" }),
  ).toBeInTheDocument();
  expect(localStorage.getItem("freeselftrack.access_token")).toBeNull();
});
