const API_URL = import.meta.env.VITE_API_URL ?? "/api";

export type AuthUser = {
  id: string;
  email: string;
  is_active: boolean;
  created_at?: string;
};

type LoginResponse = {
  access_token: string;
  token_type: string;
  user: AuthUser;
};

async function request<T>(path: string, options: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
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

