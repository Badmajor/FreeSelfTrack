import { useEffect, useState } from "react";
import { requestPasswordReset, resetPassword } from "./api";

export function PasswordRecovery({
  token,
  onDone,
}: {
  token: string | null;
  onDone: () => void;
}) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (token)
      window.history.replaceState(
        null,
        "",
        window.location.pathname + window.location.search,
      );
  }, [token]);
  return (
    <main className="shell">
      <section className="auth-panel">
        <h1>{token ? "Choose a new password" : "Reset password"}</h1>
        {!done && (
          <form
            onSubmit={async (event) => {
              event.preventDefault();
              setBusy(true);
              setError("");
              try {
                if (token) {
                  await resetPassword(token, password);
                  setPassword("");
                  setMessage("Password changed. Sign in again on all devices.");
                } else setMessage((await requestPasswordReset(email)).message);
                setDone(true);
              } catch (err) {
                setError(err instanceof Error ? err.message : "Request failed");
              } finally {
                setBusy(false);
              }
            }}
          >
            {token ? (
              <>
                <label htmlFor="reset-password">New password</label>
                <input
                  id="reset-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={12}
                  maxLength={128}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                />
              </>
            ) : (
              <>
                <label htmlFor="reset-email">Email</label>
                <input
                  id="reset-email"
                  type="email"
                  autoComplete="email"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                />
              </>
            )}
            <button className="button" disabled={busy}>
              {token ? "Save new password" : "Send reset link"}
            </button>
          </form>
        )}
        {error && <p role="alert">{error}</p>}
        {message && <p role="status">{message}</p>}
        <button className="button secondary" onClick={onDone}>
          Back to sign in
        </button>
      </section>
    </main>
  );
}
