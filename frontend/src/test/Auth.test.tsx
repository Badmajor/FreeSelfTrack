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
        if (url.endsWith("/auth/register")) return jsonResponse(registeredUser);
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
    await user.type(screen.getByLabelText("First name"), "Ada");
    await user.type(screen.getByLabelText("Last name"), "Lovelace");
    await user.type(screen.getByLabelText("Email"), "new@example.com");
    await user.type(screen.getByLabelText("Password"), "password123");
    await user.click(screen.getByRole("button", { name: "Create account" }));

    expect(await screen.findByRole("status")).toHaveTextContent(
      "Account created",
    );
    await user.type(screen.getByLabelText("Password"), "password123");
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
          password: "password123",
        }),
      }),
    );
  });
});
