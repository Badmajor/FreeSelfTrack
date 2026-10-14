import { Link } from "react-router-dom";
import { useState } from "react";
import { KeyRound, UserRoundX, UserRoundCheck } from "lucide-react";
import { LifecycleDialog } from "./LifecycleDialog";
import { TemporaryPasswordDialog } from "./TemporaryPasswordDialog";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
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
  return (
    <section className="route-page user-management-page">
      <header className="route-header">
        <h1>Users</h1>
      </header>
      {(user.is_system_admin || scopes.length > 0) && (
        <Link
          className="button compact user-create-link"
          to="/management/users/new"
        >
          Create user
        </Link>
      )}
      {secret !== null && (
        <TemporaryPasswordDialog
          secret={secret}
          onClose={() => setSecret(null)}
        />
      )}
      <div className="user-list-filters">
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
      </div>
      {users.isPending && <p role="status">Loading users...</p>}
      {(users.isError || organizations.isError) && (
        <p role="alert">Unable to load users or organizations.</p>
      )}
      {error && !blockTarget && <p role="alert">{error}</p>}
      {users.data?.items.length === 0 && <p>No users found.</p>}
      <ul className="user-directory">
        {users.data?.items.map((target) => (
          <li className="user-directory-row" key={target.id}>
            <div className="user-directory-identity">
              <Link to={`/users/${target.id}`}>
                {target.first_name} {target.last_name}
              </Link>{" "}
              {!target.is_active && <span>(Blocked)</span>}
            </div>
            <div className="user-directory-actions">
              {target.capabilities.reset_password && (
                <button
                  className="icon-button"
                  title={`Reset password for ${target.first_name} ${target.last_name}`}
                  aria-label={`Reset password for ${target.first_name} ${target.last_name}`}
                  disabled={busy || secret !== null}
                  onClick={() =>
                    void perform(
                      async () =>
                        (await issueTemporaryPassword(target.id))
                          .temporary_password,
                    )
                  }
                >
                  <KeyRound size={18} aria-hidden="true" />
                </button>
              )}
              {target.capabilities.block && (
                <button
                  className="icon-button danger"
                  title={`Block ${target.first_name} ${target.last_name}`}
                  aria-label={`Block ${target.first_name} ${target.last_name}`}
                  disabled={busy || secret !== null}
                  onClick={() => setBlockTarget(target)}
                >
                  <UserRoundX size={18} aria-hidden="true" />
                </button>
              )}
              {target.capabilities.unblock && (
                <button
                  className="icon-button"
                  title={`Unblock ${target.first_name} ${target.last_name}`}
                  aria-label={`Unblock ${target.first_name} ${target.last_name}`}
                  disabled={busy || secret !== null}
                  onClick={() =>
                    void perform(async () => {
                      await setUserBlocked(target.id, false);
                      return null;
                    })
                  }
                >
                  <UserRoundCheck size={18} aria-hidden="true" />
                </button>
              )}
            </div>
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
          {error && <p role="alert">{error}</p>}
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
