import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationCenter } from "../App";

const notification = {
  id: "notification-1",
  recipient_id: "user-1",
  task_id: "task-1",
  event_type: "status_changed",
  message: "Task status changed",
  event_data: null,
  created_at: "2026-01-02T10:00:00Z",
  read_at: null,
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("NotificationCenter", () => {
  it("shows unread count and marks a notification read when opened", async () => {
    const fetchMock = vi.fn((input: string | URL | Request) => {
      const url = String(input);
      if (url.includes("unread-count")) return Promise.resolve(new Response(JSON.stringify({ count: 1 }), { status: 200 }));
      if (url.includes("/notifications/notification-1/open")) return Promise.resolve(new Response(JSON.stringify({ ...notification, read_at: "2026-01-02T11:00:00Z" }), { status: 200 }));
      return Promise.resolve(new Response(JSON.stringify([notification]), { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });

    render(<QueryClientProvider client={queryClient}><NotificationCenter /></QueryClientProvider>);

    const toggle = await screen.findByRole("button", { name: "Notifications (1)" });
    await userEvent.click(toggle);
    const item = await screen.findByText("Task status changed");
    await userEvent.click(item);

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/notifications/notification-1/open",
      expect.objectContaining({ method: "POST" }),
    );
  });
});
