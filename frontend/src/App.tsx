import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getUnreadNotificationCount,
  listNotifications,
  login,
  logout,
  restoreSession,
  ApiError,
  openNotification,
  type AuthUser,
  type Profile,
} from "./api";
import { AuthenticatedApp } from "./WorkspaceApp";
import { AccountSecurity } from "./AccountSecurity";

export function App() {
  const queryClient = useQueryClient();
  const [restoring, setRestoring] = useState(true);
  const [restoreError, setRestoreError] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [legacyLink] = useState(() => {
    const params = new URLSearchParams(window.location.hash.slice(1));
    return params.has("verify") || params.has("reset");
  });
  useEffect(() => {
    let active = true;
    if (legacyLink)
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
    localStorage.removeItem("freeselftrack.access_token");
    localStorage.removeItem("freeselftrack.user");
    const expired = () => {
      queryClient.clear();
      setUser(null);
    };
    window.addEventListener("freeselftrack:session-ended", expired);
    restoreSession()
      .then((result) => {
        if (active) setUser(result.user);
      })
      .catch((err: unknown) => {
        if (active && !(err instanceof ApiError && err.status === 401)) {
          setRestoreError(
            err instanceof ApiError && err.status === 403
              ? "Session restoration was rejected. Open the configured application address or contact your administrator."
              : "Unable to restore your session. Try again or sign in.",
          );
        }
      })
      .finally(() => {
        if (active) setRestoring(false);
      });
    return () => {
      active = false;
      window.removeEventListener("freeselftrack:session-ended", expired);
    };
  }, [queryClient, legacyLink]);
  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setSubmitting(true);
    try {
      const result = await login(email, password);
      setUser(result.user);
      setPassword("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }
  async function signOut() {
    setError("");
    try {
      await logout();
    } catch {
      setError("Sign out failed. Try again.");
    }
  }
  function saveProfile(profile: Profile) {
    if (user) setUser({ ...user, profile });
  }
  if (restoring) return <p role="status">Restoring session...</p>;
  if (user?.must_change_password)
    return (
      <main className="shell">
        <h1>Set a permanent password</h1>
        <p>
          Your temporary password permits only a password change. Sign in again
          after changing it.
        </p>
        <AccountSecurity />
        <button type="button" onClick={() => void signOut()}>
          Sign out
        </button>
        {error && <p role="alert">{error}</p>}
      </main>
    );
  if (user)
    return (
      <>
        {error && <p role="alert">{error}</p>}
        <AuthenticatedApp
          user={user}
          onSignOut={() => void signOut()}
          onUserSaved={saveProfile}
        />
      </>
    );
  return (
    <main className="shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="eyebrow">FreeSelfTrack</div>
        <h1 id="auth-title">Welcome back</h1>
        <p className="muted">
          Sign in to continue to your workspace. Contact your administrator to
          create an account or reset your password.
        </p>
        {legacyLink && (
          <p role="status">
            Registration and password reset links are no longer supported.
            Contact your administrator.
          </p>
        )}
        {restoreError && (
          <div>
            <p role="alert">{restoreError}</p>
            <button type="button" onClick={() => window.location.reload()}>
              Retry
            </button>
          </div>
        )}
        <form onSubmit={handleSubmit}>
          <label htmlFor="email">Email</label>
          <input
            id="email"
            type="text"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label htmlFor="password">Password</label>
          <input
            id="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          {error && <p role="alert">{error}</p>}
          <button className="button" disabled={submitting}>
            {submitting ? "Working..." : "Sign in"}
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
