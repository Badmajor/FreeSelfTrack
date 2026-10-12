import { useState, type FormEvent } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  getUserCard,
  listUserMemberships,
  updateUserProfile,
  updateMyProfile,
  requestEmailChange,
  changeUserEmail,
  type AuthUser,
  type Profile,
  type UserCard,
} from "./api";

export function UserCardPage({ user, onSaved }: {
  user: AuthUser;
  onSaved: (profile: Profile) => void;
}) {
  const { userId = "" } = useParams();
  const card = useQuery({
    queryKey: ["users", userId],
    queryFn: () => getUserCard(userId),
  });
  if (card.isPending) return <p role="status">Loading user...</p>;
  if (card.isError) {
    return (
      <div role="alert">
        {card.error.message}
        <button onClick={() => void card.refetch()}>Retry</button>
      </div>
    );
  }
  return (
    <section className="route-page">
      <h1>{card.data.first_name} {card.data.last_name}</h1>
      <p>{card.data.is_active ? "Active" : "Blocked"}</p>
      <p>Joined {new Date(card.data.created_at).toLocaleDateString()}</p>
      {card.data.capabilities.edit_profile && (
        <ProfileEditor key={userId} card={card.data} self={user.id === userId} onSaved={onSaved} />
      )}
      {card.data.capabilities.change_email && (
        <EmailChangeForm key={`email-${userId}`} targetId={userId} self={user.id === userId} />
      )}
      <p>All active memberships are shown. Membership names do not grant access to these resources.</p>
      <UserMemberships key={`org-${userId}`} id={userId} scope="organizations" />
      <UserMemberships key={`project-${userId}`} id={userId} scope="projects" />
    </section>
  );
}

function ProfileEditor({ card, self, onSaved }: {
  card: UserCard;
  self: boolean;
  onSaved: (profile: Profile) => void;
}) {
  const client = useQueryClient();
  const [first, setFirst] = useState(card.first_name);
  const [last, setLast] = useState(card.last_name);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const result = self
        ? await updateMyProfile(first, last)
        : await updateUserProfile(card.id, first, last);
      if (self) onSaved(result);
      await client.invalidateQueries({ queryKey: ["users"] });
      await client.invalidateQueries({ queryKey: ["profile"] });
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to save profile");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="profile-form" onSubmit={submit}>
      <h2>Edit profile</h2>
      <label htmlFor="card-first">First name</label>
      <input id="card-first" required maxLength={100} value={first}
        onChange={event => setFirst(event.target.value)} />
      <label htmlFor="card-last">Last name</label>
      <input id="card-last" required maxLength={100} value={last}
        onChange={event => setLast(event.target.value)} />
      <button disabled={busy}>Save profile</button>
      {error && <p role="alert">{error}</p>}
      {saved && <p role="status">Profile saved.</p>}
    </form>
  );
}

export function EmailChangeForm({ targetId, self }: { targetId: string; self: boolean }) {
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      if (self) {
        const result = await requestEmailChange(email);
        setMessage(
          `${result.message} Valid until ${new Date(result.expires_at).toLocaleString()}. Previous links are cancelled.`,
        );
      } else {
        await changeUserEmail(targetId, email);
        setMessage("Email changed. Pending confirmation cancelled.");
      }
      setEmail("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to change email");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="profile-form" onSubmit={submit}>
      <h2>Change email</h2>
      <p>{self
        ? "Your current email stays valid until you confirm the new address. The latest link is valid for six hours."
        : "The address changes immediately without confirmation."}</p>
      <label htmlFor="new-email">New email</label>
      <input id="new-email" type="email" required maxLength={320} value={email}
        onChange={event => setEmail(event.target.value)} />
      <button disabled={busy}>{self ? "Send confirmation" : "Change email directly"}</button>
      {error && <p role="alert">{error}</p>}
      {message && <p role="status">{message}</p>}
    </form>
  );
}

function UserMemberships({ id, scope }: { id: string; scope: "organizations" | "projects" }) {
  const page = useInfiniteQuery({
    queryKey: ["users", id, scope],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listUserMemberships(id, scope, pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const items = page.data?.pages.flatMap(p => p.items) ?? [];
  return (
    <section>
      <h2>{scope === "organizations" ? "Organizations" : "Projects"}</h2>
      {page.isPending && <p role="status">Loading memberships...</p>}
      {page.isError && (
        <p role="alert">
          {page.error.message}
          <button onClick={() => void (page.isFetchNextPageError ? page.fetchNextPage() : page.refetch())}>
            Retry
          </button>
        </p>
      )}
      {page.isSuccess && items.length === 0 && <p>No active memberships.</p>}
      <ul>
        {items.map(item => (
          <li key={item.id}>
            {item.can_open
              ? <Link to={`/management/${scope}/${item.id}`}>{item.name}</Link>
              : <span>{item.name} (No access)</span>}
            {item.organization_name && <span> — {item.organization_name}</span>}
            {" — "}{item.role === "manager" ? "Manager" : "Member"}
          </li>
        ))}
      </ul>
      {page.hasNextPage && (
        <button disabled={page.isFetchingNextPage} onClick={() => void page.fetchNextPage()}>
          Load more {scope}
        </button>
      )}
    </section>
  );
}
