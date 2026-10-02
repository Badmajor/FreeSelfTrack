export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

const API_URL = import.meta.env.VITE_API_URL ?? "/api";

export type Profile = {
  user_id: string;
  first_name: string;
  last_name: string;
};

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

let accessToken: string | null = null;
let generation = 0;
let refreshing: Promise<LoginResponse> | null = null;

export function clearSession(): void {
  generation += 1;
  accessToken = null;
  localStorage.removeItem("freeselftrack.access_token");
  localStorage.removeItem("freeselftrack.user");
}

function endSession(): void {
  clearSession();
  window.dispatchEvent(new Event("freeselftrack:session-ended"));
}

async function authLock<T>(action: () => Promise<T>): Promise<T> {
  // Cookies are shared by tabs: serialize rotations across tabs where Web Locks is available.
  if (navigator.locks)
    return navigator.locks.request("freeselftrack-session", action);
  return action();
}

async function readResponse<T>(response: Response): Promise<T> {
  const body = (await response.json().catch(() => null)) as
    { detail?: string } | T | null;
  if (!response.ok) {
    const detail =
      body &&
      typeof body === "object" &&
      "detail" in body &&
      typeof body.detail === "string"
        ? body.detail
        : "Request failed";
    throw new ApiError(detail, response.status);
  }
  return body as T;
}

async function rawRequest(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  return fetch(`${API_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      "X-CSRF-Protection": "1",
      ...options.headers,
    },
  });
}

export function restoreSession(): Promise<LoginResponse> {
  if (!refreshing) {
    const started = generation;
    refreshing = authLock(async () => {
      const result = await readResponse<LoginResponse>(
        await rawRequest("/auth/refresh", { method: "POST" }),
      );
      if (started !== generation) throw new ApiError("Session changed", 401);
      accessToken = result.access_token;
      return result;
    })
      .catch((error: unknown) => {
        if (
          started === generation &&
          error instanceof ApiError &&
          error.status === 401
        )
          endSession();
        throw error;
      })
      .finally(() => {
        refreshing = null;
      });
  }
  return refreshing;
}

async function authenticatedRequest(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const usedToken = accessToken;
  const started = generation;
  let response = await rawRequest(path, options);
  const protectedPath =
    !path.startsWith("/auth/") ||
    [
      "/auth/password/change",
      "/auth/deactivate",
      "/auth/sessions/current",
    ].includes(path);
  const authFailure =
    response.status === 401 &&
    protectedPath &&
    (!path.startsWith("/auth/") ||
      (await response.clone().json()).detail === "Authentication required");
  if (authFailure && started === generation) {
    if (usedToken === accessToken) await restoreSession();
    if (started !== generation) throw new ApiError("Session ended", 401);
    response = await rawRequest(path, options);
    if (
      response.status === 401 &&
      (!path.startsWith("/auth/") ||
        (await response.clone().json()).detail === "Authentication required")
    )
      endSession();
  }
  return response;
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  return readResponse<T>(await authenticatedRequest(path, options));
}

export async function logout(): Promise<void> {
  // Wait for any pending rotation before revoking the cookie it sets.
  generation += 1;
  if (refreshing) await refreshing.catch(() => undefined);
  await authLock(async () => {
    const response = await rawRequest("/auth/logout", { method: "POST" });
    if (response.status !== 401) await readResponse<void>(response);
  });
  endSession();
}

export async function changePassword(
  currentPassword: string,
  newPassword: string,
): Promise<void> {
  await request<void>("/auth/password/change", {
    method: "POST",
    body: JSON.stringify({
      current_password: currentPassword,
      new_password: newPassword,
    }),
  });
  endSession();
}

export async function deactivateAccount(
  currentPassword: string,
): Promise<void> {
  await request<void>("/auth/deactivate", {
    method: "POST",
    body: JSON.stringify({ current_password: currentPassword }),
  });
  endSession();
}

export function requestPasswordReset(
  email: string,
): Promise<{ message: string }> {
  return request("/auth/password/reset-request", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function resetPassword(
  token: string,
  newPassword: string,
): Promise<void> {
  await request<void>("/auth/password/reset", {
    method: "POST",
    body: JSON.stringify({ token, new_password: newPassword }),
  });
  endSession();
}

export async function register(
  email: string,
  password: string,
  firstName: string,
  lastName: string,
): Promise<{ message: string }> {
  return request<{ message: string }>("/auth/register", {
    method: "POST",
    body: JSON.stringify({
      email,
      password,
      first_name: firstName,
      last_name: lastName,
    }),
  });
}

export async function getMyProfile(): Promise<Profile> {
  return request<Profile>("/users/me/profile");
}

export async function updateMyProfile(
  firstName: string,
  lastName: string,
): Promise<Profile> {
  return request<Profile>("/users/me/profile", {
    method: "PATCH",
    body: JSON.stringify({ first_name: firstName, last_name: lastName }),
  });
}

export async function login(
  email: string,
  password: string,
): Promise<LoginResponse> {
  generation += 1;
  const started = generation;
  if (refreshing) await refreshing.catch(() => undefined);
  return authLock(async () => {
    const result = await request<LoginResponse>("/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    if (started !== generation) throw new ApiError("Session changed", 401);
    accessToken = result.access_token;
    return result;
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

export async function deleteOrganization(
  organizationId: string,
): Promise<void> {
  await request<unknown>(`/organizations/${organizationId}`, {
    method: "DELETE",
    body: JSON.stringify({ confirm: true }),
  });
}

export async function createProject(
  organizationId: string,
  name: string,
): Promise<Project> {
  return request<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ organization_id: organizationId, name }),
  });
}

export async function listProjects(organizationId: string): Promise<Project[]> {
  return request<Project[]>(`/organizations/${organizationId}/projects`);
}

export async function listProjectMembers(
  projectId: string,
): Promise<AuthUser[]> {
  return request<AuthUser[]>(`/projects/${projectId}/members`);
}

export async function addProjectMember(
  projectId: string,
  email: string,
): Promise<AuthUser> {
  return request<AuthUser>(`/projects/${projectId}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export async function removeProjectMember(
  projectId: string,
  memberId: string,
): Promise<AuthUser> {
  return request<AuthUser>(`/projects/${projectId}/members/${memberId}`, {
    method: "DELETE",
  });
}

export async function transferProjectOwnership(
  projectId: string,
  email: string,
): Promise<Project> {
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

export type Participant = { id: string; first_name: string; last_name: string };
export type Priority = "low" | "normal" | "major" | "critical";
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
  reporter: Participant;
  assignee: Participant | null;
  watchers: Participant[];
  story_points: number | null;
  due_date: string | null;
  priority: Priority | null;
  created_at: string;
  updated_at: string;
};

export type Status = {
  id: string;
  project_id: string;
  name: string;
  position: number;
  is_active: boolean;
  is_completed: boolean;
};

export async function createStatus(
  projectId: string,
  name: string,
): Promise<Status> {
  return request<Status>("/projects/" + projectId + "/statuses", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export async function updateStatus(
  projectId: string,
  statusId: string,
  data: Partial<
    Pick<Status, "name" | "position" | "is_active" | "is_completed">
  >,
): Promise<Status> {
  return request<Status>(`/projects/${projectId}/statuses/${statusId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listStatuses(projectId: string): Promise<Status[]> {
  return request<Status[]>(`/projects/${projectId}/statuses`);
}

export async function listArchivedStatuses(
  projectId: string,
): Promise<Status[]> {
  return request<Status[]>(`/projects/${projectId}/statuses/archive`);
}

export async function archiveStatus(
  projectId: string,
  statusId: string,
): Promise<Status> {
  return request<Status>(`/projects/${projectId}/statuses/${statusId}`, {
    method: "DELETE",
  });
}

export async function restoreStatus(
  projectId: string,
  statusId: string,
): Promise<Status> {
  return request<Status>(
    `/projects/${projectId}/statuses/${statusId}/restore`,
    { method: "POST" },
  );
}


export type TaskLinkRelation = "blocks" | "depends_on" | "related";
export type TaskLinkTask = {
  id: string;
  slug: string;
  title: string;
  project_id: string;
  project_name: string;
  status_id: string;
  status_name: string;
};
export type TaskLink = {
  id: string;
  relation_type: TaskLinkRelation;
  task: TaskLinkTask;
  created_by: Participant;
  created_at: string;
};
export type TaskSearchResult = { items: TaskLinkTask[] };

export function listTaskLinks(taskId: string): Promise<TaskLink[]> {
  return request<TaskLink[]>(`/tasks/${taskId}/links`);
}
export function createTaskLink(
  taskId: string,
  targetTaskId: string,
  relationType: TaskLinkRelation,
): Promise<TaskLink> {
  return request<TaskLink>(`/tasks/${taskId}/links`, {
    method: "POST",
    body: JSON.stringify({
      target_task_id: targetTaskId,
      relation_type: relationType,
    }),
  });
}
export async function deleteTaskLink(
  taskId: string,
  linkId: string,
): Promise<void> {
  await request<unknown>(`/tasks/${taskId}/links/${linkId}`, {
    method: "DELETE",
  });
}
export function searchOrganizationTasks(
  organizationId: string,
  slug: string,
): Promise<TaskSearchResult> {
  const query = new URLSearchParams({ slug, limit: "20" });
  return request<TaskSearchResult>(
    `/organizations/${organizationId}/tasks/search?${query}`,
  );
}

export type BoardColumn = {
  status: Status;
  tasks: Task[];
  next_cursor: string | null;
};

export async function reorderStatuses(
  projectId: string,
  statusIds: string[],
): Promise<Status[]> {
  return request<Status[]>("/projects/" + projectId + "/statuses/reorder", {
    method: "POST",
    body: JSON.stringify({ status_ids: statusIds }),
  });
}
export type Board = { project_id: string; columns: BoardColumn[] };
export type TaskPage = { tasks: Task[]; next_cursor: string | null };
export type TaskHistoryEntry = {
  id: string;
  task_id: string;
  changed_by: string;
  actor: Profile;
  from_status_id?: string | null;
  to_status_id?: string | null;
  event_type: string;
  field_name?: string | null;
  old_value?: string | null;
  new_value?: string | null;
  created_at: string;
};
export type TaskHistoryPage = {
  entries: TaskHistoryEntry[];
  next_cursor: string | null;
};

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

export async function getColumnTasks(
  projectId: string,
  statusId: string,
  cursor: string,
  limit = 500,
): Promise<TaskPage> {
  return request<TaskPage>(
    "/projects/" +
      projectId +
      "/board/columns/" +
      statusId +
      "/tasks?limit=" +
      limit +
      "&cursor=" +
      encodeURIComponent(cursor),
  );
}

export async function createTask(
  projectId: string,
  data: Pick<
    Task,
    | "title"
    | "description"
    | "status_id"
    | "story_points"
    | "due_date"
    | "priority"
  >,
): Promise<Task> {
  return request<Task>("/projects/" + projectId + "/tasks", {
    method: "POST",
    body: JSON.stringify(data),
  });
}

export async function getTaskHistory(
  taskId: string,
  limit = 500,
): Promise<TaskHistoryPage> {
  return request<TaskHistoryPage>(
    "/tasks/" + taskId + "/history?limit=" + limit,
  );
}

export async function updateTask(
  taskId: string,
  data: Partial<
    Pick<
      Task,
      | "title"
      | "description"
      | "status_id"
      | "reporter_id"
      | "assignee_id"
      | "story_points"
      | "due_date"
      | "priority"
    >
  >,
): Promise<Task> {
  return request<Task>(`/tasks/${taskId}`, {
    method: "PATCH",
    body: JSON.stringify(data),
  });
}

export async function listTaskWatchers(taskId: string): Promise<Participant[]> {
  return request<Participant[]>(`/tasks/${taskId}/watchers`);
}

export async function addTaskWatcher(
  taskId: string,
  userId?: string,
): Promise<Participant[]> {
  return request<Participant[]>(`/tasks/${taskId}/watchers`, {
    method: "POST",
    body: JSON.stringify(userId ? { user_id: userId } : {}),
  });
}

export async function removeTaskWatcher(
  taskId: string,
  userId: string,
): Promise<Participant[]> {
  return request<Participant[]>(`/tasks/${taskId}/watchers/${userId}`, {
    method: "DELETE",
  });
}

export async function listNotifications(): Promise<Notification[]> {
  return request<Notification[]>("/notifications");
}

export async function getUnreadNotificationCount(): Promise<number> {
  const response = await request<{ count: number }>(
    "/notifications/unread-count",
  );
  return response.count;
}

export async function openNotification(
  notificationId: string,
): Promise<Notification> {
  return request<Notification>(`/notifications/${notificationId}/open`, {
    method: "POST",
  });
}

export function listOrganizationMembers(
  organizationId: string,
): Promise<AuthUser[]> {
  return request<AuthUser[]>(`/organizations/${organizationId}/members`);
}

export function addOrganizationMember(
  organizationId: string,
  email: string,
): Promise<AuthUser> {
  return request<AuthUser>(`/organizations/${organizationId}/members`, {
    method: "POST",
    body: JSON.stringify({ email }),
  });
}

export type ChatAttachment = {
  id: string;
  filename: string;
  media_type: string;
  state: "pending" | "ready" | "failed" | "infected";
  size: number;
};
export type ChatMessage = {
  id: string;
  task_id: string;
  sequence: number;
  author: Profile;
  text: string;
  mentions: Profile[];
  attachments: ChatAttachment[];
  created_at: string;
};
export type ChatPage = { comments: ChatMessage[]; has_more: boolean };
export function getComments(
  taskId: string,
  cursor?: { before?: number; after?: number },
): Promise<ChatPage> {
  const query = new URLSearchParams({ limit: "50" });
  if (cursor?.before !== undefined) query.set("before", String(cursor.before));
  if (cursor?.after !== undefined) query.set("after", String(cursor.after));
  return request<ChatPage>(`/tasks/${taskId}/comments?${query}`);
}
export function getComment(
  taskId: string,
  commentId: string,
): Promise<ChatMessage> {
  return request<ChatMessage>(`/tasks/${taskId}/comments/${commentId}`);
}
export function sendComment(
  taskId: string,
  text: string,
  mentionIds: string[],
  files: File[],
  requestId: string,
): Promise<ChatMessage> {
  const body = new FormData();
  body.set(
    "metadata",
    JSON.stringify({ text, mention_ids: mentionIds, request_id: requestId }),
  );
  files.forEach((file) => body.append("files", file));
  return request<ChatMessage>(`/tasks/${taskId}/comments`, {
    method: "POST",
    body,
  });
}
export async function getAttachment(
  id: string,
  preview = false,
): Promise<Blob> {
  const response = await authenticatedRequest(
    `/attachments/${id}/content?preview=${preview}`,
  );
  if (!response.ok)
    throw new ApiError("Attachment unavailable", response.status);
  return response.blob();
}
export function getProject(id: string): Promise<Project> {
  return request<Project>(`/projects/${id}`);
}

export async function verifyEmail(
  token: string,
  password: string,
): Promise<{ message: string }> {
  return request<{ message: string }>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify({ token, password }),
  });
}
