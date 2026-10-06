import { useState } from "react";
import { changePassword } from "./api";

export function AccountSecurity({
  isSystemAdmin = false,
}: {
  isSystemAdmin?: boolean;
}) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit() {
    setBusy(true);
    setError("");
    try {
      await changePassword(current, next);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  if (isSystemAdmin) {
    return (
      <section>
        <h2>Account security</h2>
        <p>
          Administrator email and password are managed through deployment configuration.
        </p>
      </section>
    );
  }
  return (
    <section>
      <h2>Account security</h2>
      <p>Changing your password signs you out on all devices.</p>
      <form
        className="profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label htmlFor="current-password">Current password</label>
        <input
          id="current-password"
          type="password"
          autoComplete="current-password"
          required
          maxLength={128}
          value={current}
          onChange={(event) => setCurrent(event.target.value)}
        />
        <label htmlFor="new-password">New password</label>
        <input
          id="new-password"
          type="password"
          autoComplete="new-password"
          required
          minLength={12}
          maxLength={128}
          value={next}
          onChange={(event) => setNext(event.target.value)}
        />
        <button className="button" disabled={busy}>
          Change password
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  );
}
