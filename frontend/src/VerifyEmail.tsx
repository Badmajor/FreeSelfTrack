import { FormEvent, useEffect, useState } from "react";

import { verifyEmail } from "./api";

export function VerifyEmail({
  token,
  onDone,
}: {
  token: string;
  onDone: () => void;
}) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [confirmed, setConfirmed] = useState(false);

  useEffect(() => {
    // Keep the token only in component memory after opening the email link.
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await verifyEmail(token, password);
      setPassword("");
      setConfirmed(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Confirmation failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <section className="auth-panel">
        <h1>Confirm your email</h1>
        {confirmed ? (
          <>
            <p role="status">
              Confirmation processed. Sign in with your account credentials.
            </p>
            <button className="button" onClick={onDone}>
              Continue to sign in
            </button>
          </>
        ) : (
          <form onSubmit={submit}>
            <p>
              Enter the password you chose when registering. Only confirm a
              registration you requested.
            </p>
            <label htmlFor="confirmation-password">Registration password</label>
            <input
              id="confirmation-password"
              type="password"
              autoComplete="current-password"
              required
              maxLength={128}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
            />
            {error && (
              <p role="alert">
                {error}. If the link expired, register again to request a new email.
              </p>
            )}
            <button className="button" disabled={busy}>
              {busy ? "Confirming..." : "Confirm email"}
            </button>
            <button
              type="button"
              className="button secondary"
              onClick={onDone}
            >
              Back to sign in
            </button>
          </form>
        )}
      </section>
    </main>
  );
}
