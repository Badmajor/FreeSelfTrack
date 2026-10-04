import { useState } from "react";
import { changePassword, deactivateAccount } from "./api";

export function AccountSecurity() {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function submit(deactivate: boolean) {
    if (
      deactivate &&
      !window.confirm(
        "Deactivate your account? You will be signed out on all devices.",
      )
    )
      return;
    setBusy(true);
    setError("");
    try {
      if (deactivate) await deactivateAccount(current);
      else await changePassword(current, next);
      setCurrent("");
      setNext("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section>
      <h2>Account security</h2>
      <p>
        Changing your password or deactivating your account signs you out on all
        devices. Transfer all organization and project ownership before
        deactivation, including archived resources.
      </p>
      <form
        className="profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(false);
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
        <button
          className="button danger"
          type="button"
          disabled={busy || !current}
          onClick={() => void submit(true)}
        >
          Deactivate account
        </button>
        {error && <p role="alert">{error}</p>}
      </form>
    </section>
  );
}
