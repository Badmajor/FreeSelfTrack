import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getUnreadNotificationCount,
  listNotifications,
  login,
  openNotification,
  register,
  type AuthUser,
  type Profile,
} from "./api";
import { VerifyEmail } from "./VerifyEmail";
import { AuthenticatedApp } from "./WorkspaceApp";

type Mode = "login" | "register";

function savedUser(): AuthUser | null {
  if (!localStorage.getItem("freeselftrack.access_token")) return null;
  try {
    return JSON.parse(
      localStorage.getItem("freeselftrack.user") ?? "null",
    ) as AuthUser | null;
  } catch {
    return null;
  }
}

export function App() {
  const [verificationToken, setVerificationToken] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).get("verify"),
  );
  const queryClient = useQueryClient();
  const initialUser = savedUser();
  const [mode, setMode] = useState<Mode>(initialUser ? "login" : "register");
  const [email, setEmail] = useState(initialUser?.email ?? "");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [user, setUser] = useState<AuthUser | null>(initialUser);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);
    try {
      if (mode === "register") {
        await register(email, password, firstName, lastName);
        setPassword("");
        setMode("login");
        setNotice("Check your email to confirm your registration, then sign in.");
      } else {
        const response = await login(email, password);
        localStorage.setItem(
          "freeselftrack.access_token",
          response.access_token,
        );
        localStorage.setItem(
          "freeselftrack.user",
          JSON.stringify(response.user),
        );
        setUser(response.user);
        setPassword("");
      }
    } catch (submitError) {
      setError(
        submitError instanceof Error ? submitError.message : "Request failed",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function signOut() {
    queryClient.clear();
    localStorage.removeItem("freeselftrack.access_token");
    localStorage.removeItem("freeselftrack.user");
    setUser(null);
    setMode("login");
    setNotice("");
  }

  function saveProfile(profile: Profile) {
    if (!user) return;
    const next = { ...user, profile };
    setUser(next);
    localStorage.setItem("freeselftrack.user", JSON.stringify(next));
  }

  if (verificationToken)
    return (
      <VerifyEmail
        token={verificationToken}
        onDone={() => {
          setVerificationToken(null);
          setMode("login");
        }}
      />
    );

  if (user)
    return (
      <AuthenticatedApp
        user={user}
        onSignOut={signOut}
        onUserSaved={saveProfile}
      />
    );

  return (
    <main className="shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="eyebrow">FreeSelfTrack</div>
        <h1 id="auth-title">
          {mode === "register" ? "Create your account" : "Welcome back"}
        </h1>
        <p className="muted">
          {mode === "register"
            ? "Set up your account to start organizing work."
            : "Sign in to continue to your workspace."}
        </p>
        <div
          className="mode-switch"
          role="tablist"
          aria-label="Authentication mode"
        >
          <button
            className={mode === "register" ? "tab active" : "tab"}
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            onClick={() => {
              setMode("register");
              setError("");
              setNotice("");
            }}
          >
            Register
          </button>
          <button
            className={mode === "login" ? "tab active" : "tab"}
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            onClick={() => {
              setMode("login");
              setError("");
              setNotice("");
            }}
          >
            Sign in
          </button>
        </div>
        <form onSubmit={handleSubmit} noValidate>
          {mode === "register" && (
            <>
              <label htmlFor="first-name">First name</label>
              <input
                id="first-name"
                value={firstName}
                onChange={(event) => setFirstName(event.target.value)}
                required
              />
              <label htmlFor="last-name">Last name</label>
              <input
                id="last-name"
                value={lastName}
                onChange={(event) => setLastName(event.target.value)}
                required
              />
            </>
          )}
          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={
              mode === "register" ? "new-password" : "current-password"
            }
            minLength={mode === "register" ? 12 : 1}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
          {notice && (
            <p className="notice" role="status">
              {notice}
            </p>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="button" type="submit" disabled={submitting}>
            {submitting
              ? "Working..."
              : mode === "register"
                ? "Create account"
                : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

type NotificationCenterProps = {
  onOpenTask?: (taskId: string, commentId?: string) => void;
};

export function NotificationCenter({ onOpenTask }: NotificationCenterProps) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: listNotifications,
    enabled: expanded,
    refetchInterval: expanded ? 3000 : false,
  });
  const unread = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: getUnreadNotificationCount,
    refetchInterval: 3000,
  });
  const open = useMutation({
    mutationFn: openNotification,
    onSuccess: (notification) => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({
        queryKey: ["notifications", "unread-count"],
      });
      let commentId: string | undefined;
      if (notification.event_data) {
        try {
          const data: unknown = JSON.parse(notification.event_data);
          if (
            data &&
            typeof data === "object" &&
            "comment_id" in data &&
            typeof data.comment_id === "string"
          )
            commentId = data.comment_id;
        } catch {
          /* Older notifications may not contain structured data. */
        }
      }
      if (notification.task_id) onOpenTask?.(notification.task_id, commentId);
    },
  });

  return (
    <div className="notification-center">
      <button
        className="button secondary compact"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        Notifications{unread.data ? ` (${unread.data})` : ""}
      </button>
      {expanded && (
        <div
          className="notification-panel"
          role="dialog"
          aria-label="Notifications"
        >
          {notifications.isPending && (
            <p className="muted">Loading notifications...</p>
          )}
          {notifications.isError && (
            <p className="error">Unable to load notifications.</p>
          )}
          {!notifications.isPending &&
            !notifications.isError &&
            !notifications.data.length && (
              <p className="muted">No notifications.</p>
            )}
          {open.isError && (
            <p className="error" role="alert">
              Unable to open notification.
            </p>
          )}
          {notifications.data?.map((notification) => (
            <button
              className={
                notification.read_at ? "notification read" : "notification"
              }
              type="button"
              key={notification.id}
              onClick={() => open.mutate(notification.id)}
              disabled={open.isPending}
            >
              <strong>{notification.message}</strong>
              <span>{new Date(notification.created_at).toLocaleString()}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
