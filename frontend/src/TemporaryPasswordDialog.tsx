import { LifecycleDialog } from "./LifecycleDialog";

export function TemporaryPasswordDialog({
  secret,
  onClose,
}: {
  secret: string;
  onClose: () => void;
}) {
  return (
    <LifecycleDialog title="Temporary password" onDismiss={onClose}>
      <h2>Temporary password</h2>
      <p>
        Share this password securely with the user. It is shown only once. The
        user must set a permanent password when signing in.
      </p>
      <output aria-label="Generated password">{secret}</output>
      <button autoFocus type="button" onClick={onClose}>
        Close password
      </button>
    </LifecycleDialog>
  );
}
