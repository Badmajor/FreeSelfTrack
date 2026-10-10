import {
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type FormEvent,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createUser,
  issueTemporaryPassword,
  listOrganizations,
  listUsers,
  setUserBlocked,
  type AuthUser,
  type UserCard,
} from "./api";

export function UsersPage({ user }: { user: AuthUser }) {
  const queryClient = useQueryClient();
  const [q, setQ] = useState("");
  const [state, setState] = useState("all");
  const [cursor, setCursor] = useState<string>();
  const [email, setEmail] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blockTarget, setBlockTarget] = useState<UserCard | null>(null);
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const scopes =
    organizations.data?.filter((org) => org.capabilities?.create_user) ?? [];
  const users = useQuery({
    queryKey: ["users", q, state, cursor],
    queryFn: () => listUsers(q, state, cursor),
  });
  async function perform(action: () => Promise<string | null>) {
    if (busy || secret !== null) return;
    setBusy(true);
    setError("");
    setSecret(null);
    try {
      setSecret(await action());
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      await queryClient.invalidateQueries({ queryKey: ["organizations"] });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(false);
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    void perform(async () => {
      const result = await createUser(
        email,
        first,
        last,
        organizationId || undefined,
      );
      setEmail("");
      setFirst("");
      setLast("");
      return result.temporary_password;
    });
  }
  return (
    <section className="management-page">
      <h1>Users</h1>
      {secret !== null && (
        <LifecycleDialog
          title="Temporary password"
          onDismiss={() => setSecret(null)}
        >
          <h2>Temporary password</h2>
          <p>
            Share this password securely with the user. It is shown only once.
            The user must set a permanent password when signing in.
          </p>
          <output aria-label="Generated password">{secret}</output>
          <button autoFocus type="button" onClick={() => setSecret(null)}>
            Close password
          </button>
        </LifecycleDialog>
      )}
      {(user.is_system_admin || scopes.length > 0) && (
        <form onSubmit={submit}>
          <h2>Create user</h2>
          <label htmlFor="user-organization">Organization</label>
          <select
            id="user-organization"
            value={organizationId}
            required={!user.is_system_admin}
            onChange={(e) => setOrganizationId(e.target.value)}
          >
            <option value="">
              {user.is_system_admin ? "No membership" : "Select organization"}
            </option>
            {scopes.map((org) => (
              <option key={org.id} value={org.id}>
                {org.name}
              </option>
            ))}
          </select>
          <label htmlFor="user-email">Email</label>
          <input
            id="user-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <label htmlFor="user-first">First name</label>
          <input
            id="user-first"
            required
            maxLength={100}
            value={first}
            onChange={(e) => setFirst(e.target.value)}
          />
          <label htmlFor="user-last">Last name</label>
          <input
            id="user-last"
            required
            maxLength={100}
            value={last}
            onChange={(e) => setLast(e.target.value)}
          />
          <button className="button" disabled={busy || secret !== null}>
            Create user
          </button>
        </form>
      )}
      <label htmlFor="user-search">Search users</label>
      <input
        id="user-search"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setCursor(undefined);
        }}
      />
      <label htmlFor="user-state">User state</label>
      <select
        id="user-state"
        value={state}
        onChange={(e) => {
          setState(e.target.value);
          setCursor(undefined);
        }}
      >
        <option value="all">All</option>
        <option value="active">Active</option>
        <option value="blocked">Blocked</option>
      </select>
      {users.isPending && <p role="status">Loading users...</p>}
      {(users.isError || organizations.isError) && (
        <p role="alert">Unable to load users or organizations.</p>
      )}
      {error && <p role="alert">{error}</p>}
      {users.data?.items.length === 0 && <p>No users found.</p>}
      <ul>
        {users.data?.items.map((target) => (
          <li key={target.id}>
            <span>
              {target.first_name} {target.last_name}
            </span>{" "}
            {!target.is_active && <span>(Blocked)</span>}
            {target.capabilities.reset_password && (
              <button
                disabled={busy || secret !== null}
                onClick={() =>
                  void perform(
                    async () =>
                      (await issueTemporaryPassword(target.id))
                        .temporary_password,
                  )
                }
              >
                Reset password for {target.first_name} {target.last_name}
              </button>
            )}
            {target.capabilities.block && (
              <button
                disabled={busy || secret !== null}
                onClick={() => setBlockTarget(target)}
              >
                Block {target.first_name} {target.last_name}
              </button>
            )}
            {target.capabilities.unblock && (
              <button
                disabled={busy || secret !== null}
                onClick={() =>
                  void perform(async () => {
                    await setUserBlocked(target.id, false);
                    return null;
                  })
                }
              >
                Unblock {target.first_name} {target.last_name}
              </button>
            )}
          </li>
        ))}
      </ul>
      {blockTarget && (
        <LifecycleDialog
          title="Confirm blocking"
          onDismiss={() => {
            if (!busy) setBlockTarget(null);
          }}
        >
          <p>
            Block {blockTarget.first_name} {blockTarget.last_name} globally? All
            sessions and memberships will be revoked. Unblocking does not
            restore memberships.
          </p>
          <button
            disabled={busy}
            onClick={() =>
              void perform(async () => {
                await setUserBlocked(blockTarget.id, true);
                setBlockTarget(null);
                return null;
              })
            }
          >
            Confirm block
          </button>
          <button disabled={busy} onClick={() => setBlockTarget(null)}>
            Cancel
          </button>
        </LifecycleDialog>
      )}
      {cursor && (
        <button onClick={() => setCursor(undefined)}>First page</button>
      )}
      {users.data?.next_cursor && (
        <button onClick={() => setCursor(users.data?.next_cursor ?? undefined)}>
          Next page
        </button>
      )}
    </section>
  );
}

function LifecycleDialog({
  title,
  onDismiss,
  children,
}: {
  title: string;
  onDismiss: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement;
    const dialog = ref.current;
    if (dialog?.showModal) dialog.showModal();
    else dialog?.setAttribute("open", "");
    return () => {
      if (dialog?.close) dialog.close();
      if (previous instanceof HTMLElement) previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        onDismiss();
      }}
    >
      {children}
    </dialog>
  );
}
