const API_URL = import.meta.env.VITE_API_URL ?? "/api";

export type AuthUser = {
  id: string;
  email: string;
  is_active: boolean;
  created_at?: string;
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

export async function register(email: string, password: string): Promise<AuthUser> {
  return request<AuthUser>("/auth/register", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function login(email: string, password: string): Promise<LoginResponse> {
  return request<LoginResponse>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
}

export async function listOrganizations(): Promise<Organization[]> {
  return request<Organization[]>("/organizations");
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
