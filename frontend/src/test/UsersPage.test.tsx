import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { UsersPage } from "../UsersPage";
import { AssigneeName } from "../KanbanView";
import { jsonResponse, renderWithQueryClient } from "./test-utils";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

it("shows the generated password once without caching it", async () => {
  const secret = "generated-test-secret";
  const fetchMock = vi.fn(
    (input: string | URL | Request, options?: RequestInit) => {
      if (String(input).endsWith("/organizations")) return jsonResponse([]);
      if (options?.method === "POST")
        return jsonResponse(
          { user: { id: "new" }, temporary_password: secret },
          201,
        );
      return jsonResponse({ items: [], next_cursor: null });
    },
  );
  vi.stubGlobal("fetch", fetchMock);
  const view = renderWithQueryClient(
    <UsersPage
      user={{
        id: "admin",
        email: "config",
        is_active: true,
        is_system_admin: true,
      }}
    />,
  );
  const actor = userEvent.setup();
  await actor.type(await screen.findByLabelText("Email"), "new@example.com");
  await actor.type(screen.getByLabelText("First name"), "New");
  await actor.type(screen.getByLabelText("Last name"), "User");
  await actor.click(screen.getByRole("button", { name: "Create user" }));
  expect(await screen.findByLabelText("Generated password")).toHaveTextContent(
    secret,
  );
  expect(JSON.stringify(localStorage)).not.toContain(secret);
  expect(JSON.stringify(sessionStorage)).not.toContain(secret);
  await actor.click(screen.getByRole("button", { name: "Close password" }));
  expect(screen.queryByText(secret)).not.toBeInTheDocument();
  view.unmount();
  renderWithQueryClient(
    <UsersPage
      user={{
        id: "admin",
        email: "config",
        is_active: true,
        is_system_admin: true,
      }}
    />,
  );
  expect(screen.queryByText(secret)).not.toBeInTheDocument();
});

it("requires confirmation before global blocking and follows backend capabilities", async () => {
  const fetchMock = vi.fn((input: string | URL | Request) => {
    if (String(input).endsWith("/organizations")) return jsonResponse([]);
    return jsonResponse({
      items: [
        {
          id: "target",
          first_name: "Other",
          last_name: "Manager",
          is_active: true,
          capabilities: { block: true, reset_password: false },
        },
      ],
      next_cursor: null,
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  renderWithQueryClient(
    <UsersPage
      user={{ id: "manager", email: "manager@example.com", is_active: true }}
    />,
  );
  const actor = userEvent.setup();
  await actor.click(
    await screen.findByRole("button", { name: "Block Other Manager" }),
  );
  expect(
    screen.getByRole("dialog", { name: "Confirm blocking" }),
  ).toHaveTextContent("globally");
  expect(
    screen.queryByRole("button", { name: /Reset password/ }),
  ).not.toBeInTheDocument();
  expect(
    fetchMock.mock.calls.some(([path]) => String(path).endsWith("/block")),
  ).toBe(false);
  await actor.click(screen.getByRole("button", { name: "Confirm block" }));
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/users/target/block",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ confirm: true }),
    }),
  );
});

it("strikes through blocked assignees with a readable reason", () => {
  renderWithQueryClient(
    <AssigneeName
      participant={{
        first_name: "Blocked",
        last_name: "Person",
        is_active: false,
      }}
    />,
  );
  expect(screen.getByText("Blocked Person").tagName).toBe("S");
  expect(screen.getByText("(Blocked)")).toBeInTheDocument();
});
