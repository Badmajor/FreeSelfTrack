import { useState } from "react";
import { confirmEmailChange } from "./api";

export function EmailChangeConfirmation({
  token,
  email,
  onDone,
  onClose,
  onSignOut,
}: {
  token: string;
  email: string;
  onDone: () => void;
  onClose: () => void;
  onSignOut: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function confirm() {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      await confirmEmailChange(token);
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to confirm email change");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="shell">
      <section>
        <h1>Confirm email change</h1>
        <p>Signed in as {email}. Confirm only a change requested by this account.</p>
        <button disabled={busy} onClick={() => void confirm()}>Confirm new email</button>
        <button disabled={busy} onClick={onSignOut}>Sign in to another account</button>
        <button disabled={busy} onClick={onClose}>Close confirmation</button>
        {error && <p role="alert">{error}</p>}
      </section>
    </main>
  );
}
