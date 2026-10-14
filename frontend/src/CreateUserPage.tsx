import { Link } from "react-router-dom";
import { useState, type FormEvent } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { createUser, listOrganizations, type AuthUser } from "./api";
import { TemporaryPasswordDialog } from "./TemporaryPasswordDialog";

export function CreateUserPage({ user }: { user: AuthUser }) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [organizationId, setOrganizationId] = useState("");
  const [secret, setSecret] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const scopes =
    organizations.data?.filter((org) => org.capabilities?.create_user) ?? [];
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
    <section className="route-page user-management-page">
      <header className="route-header">
        <h1>Create user</h1>
      </header>
      <Link className="text-link" to="/management/users">
        Back to users
      </Link>
      {secret !== null && (
        <TemporaryPasswordDialog
          secret={secret}
          onClose={() => setSecret(null)}
        />
      )}
      {organizations.isPending ? (
        <p role="status">Loading organizations...</p>
      ) : organizations.isError ? (
        <div>
          <p role="alert">Unable to load organizations.</p>
          <button onClick={() => void organizations.refetch()}>Retry</button>
        </div>
      ) : user.is_system_admin || scopes.length > 0 ? (
        <form className="management-form user-create-form" onSubmit={submit}>
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
          <div className="user-name-fields">
            <div>
              <label htmlFor="user-first">First name</label>
              <input
                id="user-first"
                required
                maxLength={100}
                value={first}
                onChange={(e) => setFirst(e.target.value)}
              />
            </div>
            <div>
              <label htmlFor="user-last">Last name</label>
              <input
                id="user-last"
                required
                maxLength={100}
                value={last}
                onChange={(e) => setLast(e.target.value)}
              />
            </div>
          </div>
          <button className="button compact" disabled={busy || secret !== null}>
            Create user
          </button>
        </form>
      ) : (
        <p role="alert">You do not have permission to create users.</p>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
