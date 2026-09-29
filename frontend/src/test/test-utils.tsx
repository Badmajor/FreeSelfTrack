import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions, type RenderResult } from "@testing-library/react";
import type { ReactElement } from "react";

import type { Board, Project, Task } from "../api";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

export function renderWithQueryClient(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper">,
): RenderResult {
  const queryClient = createTestQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>,
    options,
  );
}

export const testProject: Project = {
  id: "project-1",
  organization_id: "organization-1",
  owner_id: "owner-1",
  name: "Product",
};

export function makeTask(overrides: Partial<Task> = {}): Task {
  return {
    id: "task-1",
    project_id: testProject.id,
    status_id: "status-backlog",
    slug: "PRO-1",
    title: "First task",
    description: null,
    created_by: "owner-1",
    reporter_id: "owner-1",
    assignee_id: null,
    assignee: null,
    watchers: [],
    created_at: "2026-01-01T10:00:00Z",
    updated_at: "2026-01-02T10:00:00Z",
    ...overrides,
  };
}

export function makeBoard(task = makeTask()): Board {
  return {
    project_id: testProject.id,
    columns: [
      {
        status: { id: "status-backlog", project_id: testProject.id, name: "Backlog", position: 0, is_active: true },
        tasks: [task],
        next_cursor: null,
      },
      {
        status: { id: "status-done", project_id: testProject.id, name: "Done", position: 1, is_active: true },
        tasks: [],
        next_cursor: null,
      },
    ],
  };
}

export function jsonResponse(body: unknown, status = 200): Promise<Response> {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}
