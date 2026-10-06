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
  register,
  type AuthUser,
  type Profile,
} from "./api";
import { PasswordRecovery } from "./PasswordRecovery";
import { VerifyEmail } from "./VerifyEmail";
import { AuthenticatedApp } from "./WorkspaceApp";

type Mode = "login" | "register";

export function App() {
  const [verificationToken, setVerificationToken] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).get("verify"),
  );
  const queryClient = useQueryClient();
  const [resetToken, setResetToken] = useState(() =>
    new URLSearchParams(window.location.hash.slice(1)).get("reset"),
  );
  const [recovering, setRecovering] = useState(false);
  const [restoring, setRestoring] = useState(!verificationToken && !resetToken);
  const [restoreError, setRestoreError] = useState("");
  const [mode, setMode] = useState<Mode>("register");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [user, setUser] = useState<AuthUser | null>(null);
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
        setNotice(
          "Check your email to confirm your registration, then sign in.",
        );
      } else {
        const response = await login(email, password);
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

  useEffect(() => {
    let active = true;
    localStorage.removeItem("freeselftrack.access_token");
    localStorage.removeItem("freeselftrack.user");
    const expired = () => {
      queryClient.clear();
      setUser(null);
      setMode("login");
      setNotice("");
    };
    window.addEventListener("freeselftrack:session-ended", expired);
    if (!verificationToken && !resetToken) {
      restoreSession()
        .then((result) => {
          if (active) setUser(result.user);
        })
        .catch((err: unknown) => {
          if (active && !(err instanceof ApiError && err.status === 401)) {
            setMode("login");
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
    }
    return () => {
      active = false;
      window.removeEventListener("freeselftrack:session-ended", expired);
    };
    // Startup restoration only; completing an email flow leads to explicit sign-in.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queryClient]);

  async function signOut() {
    setError("");
    try {
      await logout();
    } catch {
      setError("Sign out failed. Try again.");
    }
  }

  function saveProfile(profile: Profile) {
    if (!user) return;
    const next = { ...user, profile };
    setUser(next);
  }

  if (resetToken || recovering)
    return (
      <PasswordRecovery
        token={resetToken}
        onDone={() => {
          setResetToken(null);
          setRecovering(false);
          setRestoring(false);
          setMode("login");
        }}
      />
    );

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

  if (restoring) return <p role="status">Restoring session...</p>;
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
        {restoreError && (
          <div>
            <p role="alert">{restoreError}</p>
            <button
              className="button secondary"
              type="button"
              onClick={() => window.location.reload()}
            >
              Retry
            </button>
          </div>
        )}
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
        <button
          className="text-link"
          type="button"
          onClick={() => setRecovering(true)}
        >
          Forgot password?
        </button>
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
            type={mode === "register" ? "email" : "text"}
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
            maxLength={mode === "register" ? 128 : undefined}
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
