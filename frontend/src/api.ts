const API_URL = import.meta.env.VITE_API_URL ?? "/api";

export type Profile = { user_id: string; first_name: string; last_name: string };

export type AuthUser = {
  id: string;
  email: string;
  is_active: boolean;
  created_at?: string;
  profile?: Profile;
};

export type Organization = {
  id: string;
  owner_id: string;
  name: string;
  deleted_at?: string | null;
};

export type Project = {
  id: string;
  organization_id: string;
  owner_id: string;
  name: string;
  deleted_at?: string | null;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

function authHeaders(): HeadersInit {
  const token = localStorage.getItem("freeselftrack.access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
      ...options.headers,
    },
  });

  const body = (await response.json().catch(() => null)) as
    | { detail?: string }
    | T
    | null;
  if (!response.ok) {
    const detail =
      body && typeof body === "object" && "detail" in body && typeof body.detail === "string"
        ? body.detail
        : "Request failed";
    throw new Error(detail);
  }
  return body as T;
}

export async function register(email: string, password: string, firstName: string, lastName: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password, first_name: firstName, last_name: lastName }),
  });
}

export async function getMyProfile(): Promise<Profile> {
  return request<Profile>("/users/me/profile");
}

export async function updateMyProfile(firstName: string, lastName: string): Promise<Profile> {
  return request<Profile>("/users/me/profile", {
    method: "PATCH",
    body: JSON.stringify({ first_name: firstName, last_name: lastName }),
  });
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function createOrganization(name: string): Promise<Organization> {
  return request<Organization>("/organizations", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function listOrganizations(): Promise<Organization[]> {
  return request<Organization[]>("/organizations");
}

export async function createProject(organizationId: string, name: string): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ organization_id: organizationId, name }),
  });
}

export async function listProjects(organizationId: string): Promise<Project[]> {
  return request<Project[]>(`/organizations/${organizationId}/projects`);
}

export async function listProjectMembers(projectId: string): Promise<AuthUser[]> {
  return request<AuthUser[]>(`/projects/${projectId}/members`);
}

export async function addProjectMember(projectId: string, email: string): Promise<AuthUser> {
  return request<AuthUser>(`/projects/${projectId}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function removeProjectMember(projectId: string, memberId: string): Promise<AuthUser> {
  return request<AuthUser>(`/projects/${projectId}/members/${memberId}`, { method: "DELETE" });
}

export async function transferProjectOwnership(projectId: string, email: string): Promise<Project> {
  return request<Project>(`/projects/${projectId}/transfer-ownership`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function deleteProject(projectId: string): Promise<void> {
  await request<unknown>(`/projects/${projectId}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm: true }),
  });
}


export type UserSummary = {
  id: string;
  email: string;
};

export type Assignee = { id: string; first_name: string; last_name: string };
export type Task = {
  id: string;
  project_id: string;
  status_id: string;
  slug: string;
  title: string;
  description: string | null;
  created_by: string;
  reporter_id: string;
  assignee_id: string | null;
  assignee: Assignee | null;
  watchers: UserSummary[];
  created_at: string;
  updated_at: string;
};

export type Status = { id: string; project_id: string; name: string; position: number; is_active: boolean };

export type BoardColumn = { status: Status; tasks: Task[]; next_cursor: string | null };
export type Board = { project_id: string; columns: BoardColumn[] };
export type TaskPage = { tasks: Task[]; next_cursor: string | null };
export type TaskHistoryEntry = { id: string; task_id: string; changed_by: string; actor: Profile; from_status_id?: string | null; to_status_id?: string | null; event_type: string; field_name?: string | null; old_value?: string | null; new_value?: string | null; created_at: string };
export type TaskHistoryPage = { entries: TaskHistoryEntry[]; next_cursor: string | null };

export type Notification = {
  id: string;
  recipient_id: string;
  task_id: string | null;
  event_type: string;
  message: string;
  event_data: string | null;
  created_at: string;
  read_at: string | null;
};

export async function getTask(taskId: string): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`);
}

export async function getBoard(projectId: string, limit = 500): Promise<Board> {
  return request<Board>("/projects/" + projectId + "/board?limit=" + limit);
}

export async function getColumnTasks(projectId: string, statusId: string, cursor: string, limit = 500): Promise<TaskPage> {
  return request<TaskPage>("/projects/" + projectId + "/board/columns/" + statusId + "/tasks?limit=" + limit + "&cursor=" + encodeURIComponent(cursor));
}

export async function createTask(projectId: string, data: Pick<Task, "title" | "description" | "status_id">): Promise<Task> {
  return request<Task>("/projects/" + projectId + "/tasks", { method: "POST", body: JSON.stringify(data) });
}

export async function getTaskHistory(taskId: string, limit = 500): Promise<TaskHistoryPage> {
  return request<TaskHistoryPage>("/tasks/" + taskId + "/history?limit=" + limit);
}

export async function updateTask(
  taskId: string,
  data: Partial<Pick<Task, "title" | "description" | "status_id" | "reporter_id" | "assignee_id">>,
): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listTaskWatchers(taskId: string): Promise<UserSummary[]> {
  return request<UserSummary[]>(`/tasks/${taskId}/watchers`);
}

export async function addTaskWatcher(
  taskId: string,
  userId?: string,
): Promise<UserSummary[]> {
  return request<UserSummary[]>(`/tasks/${taskId}/watchers`, {
    method: "POST",
    body: JSON.stringify(userId ? { user_id: userId } : {}),
  });
}

export async function removeTaskWatcher(taskId: string, userId: string): Promise<UserSummary[]> {
  return request<UserSummary[]>(`/tasks/${taskId}/watchers/${userId}`, { method: "DELETE" });
}

export async function listNotifications(): Promise<Notification[]> {
  return request<Notification[]>("/notifications");
}

export async function getUnreadNotificationCount(): Promise<number> {
  const response = await request<{ count: number }>("/notifications/unread-count");
  return response.count;
}

export async function openNotification(notificationId: string): Promise<Notification> {
  return request<Notification>(`/notifications/${notificationId}/open`, { method: "POST" });
}
