import { QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { AuthenticatedApp } from "../WorkspaceApp";
import { CreateUserPage } from "../CreateUserPage";
import { UsersPage } from "../UsersPage";
import {
  createTestQueryClient,
  jsonResponse,
  renderWithQueryClient,
} from "./test-utils";

const admin = {
  id: "admin",
  email: "admin@example.com",
  is_active: true,
  is_system_admin: true,
};
const member = { ...admin, is_system_admin: false };
const allowed = {
  id: "allowed",
  name: "Allowed organization",
  capabilities: { create_user: true },
};
const denied = {
  id: "denied",
  name: "Other organization",
  capabilities: { create_user: false },
};
const target = {
  id: "target",
  first_name: "Other",
  last_name: "Person",
  is_active: true,
  capabilities: { reset_password: true, block: true, unblock: false },
};
const page = (items: unknown[] = [], next_cursor: string | null = null) => ({
  items,
  next_cursor,
});

function mockApi(organizations = [allowed, denied]) {
  const mock = vi.fn(
    (
      input: string | URL | Request,
      _options?: RequestInit,
    ): Promise<Response> => {
      void _options;
      const url = String(input);
      if (url.includes("/organizations"))
        return jsonResponse(page(organizations));
      if (url.includes("/unread-count")) return jsonResponse({ count: 0 });
      return jsonResponse(page());
    },
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}
function route(path: string, user = admin) {
  const client = createTestQueryClient();
  const view = render(
    <MemoryRouter initialEntries={[path]}>
      <QueryClientProvider client={client}>
        <AuthenticatedApp
          user={user}
          onSignOut={() => {}}
          onUserSaved={() => {}}
        />
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { ...view, client };
}
async function fillForm() {
  const actor = userEvent.setup();
  await actor.type(await screen.findByLabelText("Email"), "new@example.com");
  await actor.type(screen.getByLabelText("First name"), "New");
  await actor.type(screen.getByLabelText("Last name"), "Person");
  return actor;
}
afterEach(() => vi.unstubAllGlobals());

it("separates direct routes, empty-list navigation and return to a refreshed directory", async () => {
  const mock = mockApi();
  const view = route("/management/users");
  expect(await screen.findByText("No users found.")).toBeInTheDocument();
  expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  const actor = userEvent.setup();
  await actor.click(screen.getByRole("link", { name: "Create user" }));
  expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  expect(screen.queryByLabelText("Search users")).not.toBeInTheDocument();
  await actor.click(screen.getByRole("link", { name: "Back to users" }));
  expect(await screen.findByLabelText("Search users")).toBeInTheDocument();
  view.unmount();
  route("/management/users/new");
  expect(await screen.findByLabelText("Email")).toBeInTheDocument();
  expect(
    mock.mock.calls.some(([url]) => String(url).startsWith("/api/users?")),
  ).toBe(true);
});

it("denies the direct creation route and creation link without backend grants", async () => {
  mockApi([denied]);
  const view = route("/management/users/new", member);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "do not have permission",
  );
  expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  view.unmount();
  route("/management/users", member);
  await screen.findByText("No users found.");
  expect(
    screen.queryByRole("link", { name: "Create user" }),
  ).not.toBeInTheDocument();
});

it("creates for OM only in a permitted organization, invalidates the list and never caches the password", async () => {
  const mock = mockApi();
  let created = false;
  mock.mockImplementation((input, options) => {
    if (options?.method === "POST") {
      created = true;
      return jsonResponse(
        { user: { id: "new" }, temporary_password: "one-time-secret" },
        201,
      );
    }
    if (String(input).includes("/organizations"))
      return jsonResponse(page([allowed, denied]));
    if (String(input).includes("/unread-count"))
      return jsonResponse({ count: 0 });
    return jsonResponse(page(created ? [target] : []));
  });
  const { client } = route("/management/users", member);
  const actor = userEvent.setup();
  await actor.click(await screen.findByRole("link", { name: "Create user" }));
  await fillForm();
  expect(
    screen.queryByRole("option", { name: denied.name }),
  ).not.toBeInTheDocument();
  await actor.click(screen.getByRole("button", { name: "Create user" }));
  expect(mock.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0,
  );
  await actor.selectOptions(screen.getByLabelText("Organization"), "allowed");
  await actor.click(screen.getByRole("button", { name: "Create user" }));
  expect(await screen.findByLabelText("Generated password")).toHaveTextContent(
    "one-time-secret",
  );
  expect(mock).toHaveBeenCalledWith(
    "/api/organizations/allowed/users",
    expect.objectContaining({ method: "POST" }),
  );
  expect(
    JSON.stringify(
      client
        .getQueryCache()
        .getAll()
        .map((q) => q.state.data),
    ),
  ).not.toContain("one-time-secret");
  await actor.click(screen.getByRole("button", { name: "Close password" }));
  await actor.click(screen.getByRole("link", { name: "Back to users" }));
  expect(
    await screen.findByRole("link", { name: "Other Person" }),
  ).toHaveAttribute("href", "/users/target");
  await actor.click(screen.getByRole("link", { name: "Create user" }));
  expect(screen.queryByText("one-time-secret")).not.toBeInTheDocument();
});

it("shows organization loading and errors, then allows retry", async () => {
  let resolve!: (r: Response) => void;
  const mock = mockApi();
  mock.mockReturnValueOnce(
    new Promise((r) => {
      resolve = r;
    }),
  );
  renderWithQueryClient(<CreateUserPage user={admin} />);
  expect(screen.getByRole("status")).toHaveTextContent("Loading organizations");
  expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
  await act(async () =>
    resolve(await jsonResponse({ detail: "Unavailable" }, 503)),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to load organizations",
  );
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByLabelText("Email")).toBeInTheDocument();
});

it("validates required fields and email, disables duplicate creation, and shows API rejection", async () => {
  const mock = mockApi([]);
  let resolve!: (r: Response) => void;
  mock.mockImplementation((_input, options) =>
    options?.method === "POST"
      ? new Promise((r) => {
          resolve = r;
        })
      : jsonResponse(page()),
  );
  renderWithQueryClient(<CreateUserPage user={admin} />);
  const actor = userEvent.setup();
  await actor.click(await screen.findByRole("button", { name: "Create user" }));
  expect(mock.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0,
  );
  await fillForm();
  await actor.clear(screen.getByLabelText("Email"));
  await actor.type(screen.getByLabelText("Email"), "invalid");
  await actor.click(screen.getByRole("button", { name: "Create user" }));
  expect(mock.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    0,
  );
  await actor.clear(screen.getByLabelText("Email"));
  await actor.type(screen.getByLabelText("Email"), "new@example.com");
  await actor.dblClick(screen.getByRole("button", { name: "Create user" }));
  expect(mock.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    1,
  );
  expect(mock).toHaveBeenCalledWith(
    "/api/users",
    expect.objectContaining({ method: "POST" }),
  );
  expect(screen.getByRole("button", { name: "Create user" })).toBeDisabled();
  await act(async () =>
    resolve(await jsonResponse({ detail: "Creation forbidden" }, 403)),
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Creation forbidden",
  );
  expect(screen.getByRole("button", { name: "Create user" })).toBeEnabled();
});

it("preserves server search, state and pagination, including empty and failed results", async () => {
  const mock = mockApi();
  mock.mockImplementation((input) => {
    const url = String(input);
    if (url.includes("organizations")) return jsonResponse(page());
    if (url.includes("state=blocked"))
      return jsonResponse({ detail: "Unavailable" }, 503);
    if (url.includes("q=nobody")) return jsonResponse(page());
    return jsonResponse(
      page([target], url.includes("cursor=") ? null : "next"),
    );
  });
  renderWithQueryClient(<UsersPage user={admin} />);
  const actor = userEvent.setup();
  await actor.click(await screen.findByRole("button", { name: "Next page" }));
  await waitFor(() =>
    expect(mock).toHaveBeenCalledWith(
      "/api/users?q=&state=all&cursor=next",
      expect.anything(),
    ),
  );
  await actor.click(await screen.findByRole("button", { name: "First page" }));
  await actor.type(screen.getByLabelText("Search users"), "nobody");
  expect(await screen.findByText("No users found.")).toBeInTheDocument();
  await actor.selectOptions(screen.getByLabelText("User state"), "active");
  await waitFor(() =>
    expect(mock).toHaveBeenCalledWith(
      "/api/users?q=nobody&state=active",
      expect.anything(),
    ),
  );
  await actor.selectOptions(screen.getByLabelText("User state"), "blocked");
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Unable to load users",
  );
});

it("provides named icon actions, keyboard cancel/focus, pending guards and errors inside confirmation", async () => {
  const mock = mockApi();
  let resolve!: (r: Response) => void;
  mock.mockImplementation((input, options) => {
    if (options?.method === "POST")
      return new Promise((r) => {
        resolve = r;
      });
    return jsonResponse(
      page(
        String(input).includes("organizations")
          ? []
          : [
              target,
              {
                ...target,
                id: "protected",
                first_name: "Protected",
                capabilities: {},
              },
            ],
      ),
    );
  });
  renderWithQueryClient(<UsersPage user={admin} />);
  const actor = userEvent.setup();
  const block = await screen.findByRole("button", {
    name: "Block Other Person",
  });
  expect(block).toHaveAttribute("title", "Block Other Person");
  expect(block.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  expect(
    screen.queryByRole("button", { name: /Protected/ }),
  ).not.toBeInTheDocument();
  block.focus();
  await actor.keyboard("{Enter}");
  await actor.click(screen.getByRole("button", { name: "Cancel" }));
  expect(block).toHaveFocus();
  await actor.keyboard("{Enter}");
  await actor.dblClick(screen.getByRole("button", { name: "Confirm block" }));
  expect(mock.mock.calls.filter(([, o]) => o?.method === "POST")).toHaveLength(
    1,
  );
  expect(screen.getByRole("button", { name: "Cancel" })).toBeDisabled();
  await act(async () =>
    resolve(await jsonResponse({ detail: "Block forbidden" }, 403)),
  );
  expect(
    within(screen.getByRole("dialog")).getByRole("alert"),
  ).toHaveTextContent("Block forbidden");
});

it("resets a password once, then unblocks and refreshes the directory", async () => {
  const mock = mockApi();
  let blocked = true;
  mock.mockImplementation((input, options) => {
    const url = String(input);
    if (url.endsWith("temporary-password"))
      return jsonResponse({ temporary_password: "reset-secret", user: {} });
    if (options?.method === "POST") {
      blocked = false;
      return jsonResponse({});
    }
    if (url.includes("organizations")) return jsonResponse(page());
    return jsonResponse(
      page([
        {
          ...target,
          is_active: !blocked,
          capabilities: { reset_password: true, unblock: blocked },
        },
      ]),
    );
  });
  renderWithQueryClient(<UsersPage user={admin} />);
  const actor = userEvent.setup();
  await actor.click(
    await screen.findByRole("button", {
      name: "Reset password for Other Person",
    }),
  );
  expect(await screen.findByLabelText("Generated password")).toHaveTextContent(
    "reset-secret",
  );
  expect(
    screen.getByRole("button", { name: "Reset password for Other Person" }),
  ).toBeDisabled();
  await actor.click(screen.getByRole("button", { name: "Close password" }));
  expect(screen.queryByText("reset-secret")).not.toBeInTheDocument();
  const unblock = screen.getByRole("button", { name: "Unblock Other Person" });
  expect(unblock).toHaveAttribute("title", "Unblock Other Person");
  await actor.click(unblock);
  await waitFor(() =>
    expect(screen.queryByText("(Blocked)")).not.toBeInTheDocument(),
  );
  expect(mock).toHaveBeenCalledWith(
    "/api/users/target/unblock",
    expect.objectContaining({ method: "POST" }),
  );
});

it.each([
  ["Reset password for Other Person", { reset_password: true }],
  ["Unblock Other Person", { unblock: true }],
])("shows API errors for %s and enables retry", async (name, capabilities) => {
  const mock = mockApi();
  mock.mockImplementation((input, options) => {
    if (options?.method === "POST")
      return jsonResponse({ detail: "Action forbidden" }, 403);
    return jsonResponse(page(String(input).includes("organizations") ? [] : [
      { ...target, capabilities },
    ]));
  });
  renderWithQueryClient(<UsersPage user={admin} />);
  const button = await screen.findByRole("button", { name });
  await userEvent.click(button);
  expect(await screen.findByRole("alert")).toHaveTextContent("Action forbidden");
  expect(button).toBeEnabled();
  expect(screen.queryByLabelText("Generated password")).not.toBeInTheDocument();
});
