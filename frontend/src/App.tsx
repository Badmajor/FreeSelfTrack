import { FormEvent, useState } from "react";

import { login, register, type AuthUser } from "./api";

type Mode = "login" | "register";

const savedToken = localStorage.getItem("freeselftrack.access_token");
const savedUser = localStorage.getItem("freeselftrack.user");

export function App() {
  const [mode, setMode] = useState<Mode>(savedToken ? "login" : "register");
  const [email, setEmail] = useState(savedUser ? JSON.parse(savedUser).email : "");
  const [password, setPassword] = useState("");
  const [user, setUser] = useState<AuthUser | null>(savedToken && savedUser ? JSON.parse(savedUser) : null);
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
        await register(email, password);
        setPassword("");
        setMode("login");
        setNotice("Account created. Sign in to continue.");
      } else {
        const response = await login(email, password);
        localStorage.setItem("freeselftrack.access_token", response.access_token);
        localStorage.setItem("freeselftrack.user", JSON.stringify(response.user));
        setUser(response.user);
        setPassword("");
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  function signOut() {
    localStorage.removeItem("freeselftrack.access_token");
    localStorage.removeItem("freeselftrack.user");
    setUser(null);
    setMode("login");
    setNotice("");
  }

  if (user) {
    return (
      <main className="shell">
        <section className="welcome-panel" aria-labelledby="welcome-title">
          <div className="eyebrow">FreeSelfTrack</div>
          <h1 id="welcome-title">You are signed in.</h1>
          <p className="muted">{user.email}</p>
          <button className="button secondary" type="button" onClick={signOut}>
            Sign out
          </button>
        </section>
      </main>
    );
  }

  return (
    <main className="shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="eyebrow">FreeSelfTrack</div>
        <h1 id="auth-title">{mode === "register" ? "Create your account" : "Welcome back"}</h1>
        <p className="muted">
          {mode === "register"
            ? "Set up your account to start organizing work."
            : "Sign in to continue to your workspace."}
        </p>

        <div className="mode-switch" role="tablist" aria-label="Authentication mode">
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
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            minLength={mode === "register" ? 8 : 1}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {notice && <p className="notice" role="status">{notice}</p>}
          {error && <p className="error" role="alert">{error}</p>}

          <button className="button" type="submit" disabled={submitting}>
            {submitting ? "Working..." : mode === "register" ? "Create account" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

