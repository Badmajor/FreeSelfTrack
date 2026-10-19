import { useEffect, useRef, useState, type ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useBlocker, useLocation, useNavigate, useOutletContext, useParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { ApiError, createOrganization, deleteOrganization, getOrganization, listOrganizationPage, updateResource, type AuthUser, type Organization } from "./api";
import { EntityAudit } from "./EntityAudit";
import { LifecycleDialog } from "./LifecycleDialog";

const archiveConsequences = "This archives the organization and all its projects and tasks. Memberships become inactive and access changes. Restoring does not restore previous memberships or permissions.";

function OrganizationPage({ title, children }: { title: string; children: ReactNode }) {
  return <section className="route-page organization-management-page">
    <header className="route-header"><div className="eyebrow">Management</div><h1>{title}</h1></header>
    {children}
  </section>;
}

function RequestError({ error, retry }: { error: Error; retry?: () => void }) {
  return <div role="alert" className="error"><p>{error.message}</p>{retry &&
    <button className="button secondary" onClick={retry}>Retry</button>}</div>;
}

function UnsavedChanges({ dirty }: { dirty: boolean }) {
  const { onDirtyChange } = useOutletContext<{ onDirtyChange: (dirty: boolean) => void }>();
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);
  const blocker = useBlocker(({ currentLocation, nextLocation }) => dirty &&
    (currentLocation.pathname !== nextLocation.pathname || currentLocation.search !== nextLocation.search));
  useEffect(() => {
    if (!dirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  if (blocker.state !== "blocked") return null;
  return <LifecycleDialog title="Discard unsaved changes?" onDismiss={() => blocker.reset()}>
    <h2>Discard unsaved changes?</h2><p>Your changes have not been saved.</p>
    <div className="organization-actions" onKeyDown={event => {
      if (event.key !== "Tab") return;
      const buttons = event.currentTarget.querySelectorAll("button");
      const target = event.shiftKey ? buttons[buttons.length - 1] : buttons[0];
      const edge = event.shiftKey ? buttons[0] : buttons[buttons.length - 1];
      if (document.activeElement === edge) { event.preventDefault(); target.focus(); }
    }}>
      <button autoFocus className="button secondary" onClick={() => blocker.reset()}>Stay on page</button>
      <button className="button danger" onClick={() => blocker.proceed()}>Discard changes</button>
    </div>
  </LifecycleDialog>;
}

export function OrganizationManagementPage({ user }: { user: AuthUser }) {
  const { organizationId } = useParams();
  const location = useLocation();
  const organizations = useInfiniteQuery({
    queryKey: ["organizations", "pages"], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listOrganizationPage(pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const detail = useQuery({ queryKey: ["organization", organizationId],
    queryFn: () => getOrganization(organizationId!), enabled: Boolean(organizationId), retry: false });
  const items = organizations.data?.pages.flatMap(page => page.items) ?? [];
  const [pickerOpen, setPickerOpen] = useState(false);
  const [wide, setWide] = useState(true);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia("(min-width: 1100px)");
    const update = () => setWide(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);
  const picker = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    setPickerOpen(false);
    // Return focus to the mobile selector before its links become hidden.
    if (picker.current?.contains(document.activeElement)) picker.current.querySelector("summary")?.focus();
  }, [organizationId]);
  return <OrganizationPage title="Organizations">
    <nav className="organization-actions organization-navigation" aria-label="Organization management">
      <Link className="button secondary" to="/archive">Archived organizations</Link>
      {user.is_system_admin && <Link className="button secondary" to="/management/organizations/new"><Plus size={18} aria-hidden="true" />Create organization</Link>}
    </nav>
    {location.state?.organizationArchived && <p role="status">Organization archived.</p>}
    {organizations.isSuccess && !items.length && <p role="status">No organizations yet.{user.is_system_admin && " Use Create organization to get started."}</p>}
    <div className="organization-grid">
      <details ref={picker} className="organization-picker" open={wide || pickerOpen} onToggle={event => { if (!wide) setPickerOpen(event.currentTarget.open); }}>
        <summary>Choose organization{detail.data ? `: ${detail.data.name}` : ""}</summary>
        <nav aria-label="Available organizations" className="organization-catalog">
          <h2>Available organizations</h2>
          {organizations.isPending && <p role="status">Loading organizations...</p>}
          {organizations.isError && <RequestError error={organizations.error} retry={() => void organizations.refetch()} />}
          {items.map(org => <Link key={org.id} className={`management-item${org.id === organizationId ? " active" : ""}`}
            aria-current={org.id === organizationId ? "page" : undefined} to={`/management/organizations/${org.id}`}>{org.name}</Link>)}
          {organizations.hasNextPage && <button className="button secondary" disabled={organizations.isFetchingNextPage}
            onClick={() => void organizations.fetchNextPage()}>{organizations.isFetchingNextPage ? "Loading organizations..." : "Load more organizations"}</button>}
        </nav>
      </details>
      <section className="organization-detail" aria-label="Selected organization">
        {!organizationId ? <p>Select an organization to view details.</p> : detail.isPending ? <p role="status">Loading organization...</p> :
          detail.isError && detail.error instanceof ApiError && [401, 403, 404].includes(detail.error.status) ?
            <p role="alert">Organization not found or unavailable.</p> : <>
            {detail.isError && <RequestError error={detail.error} retry={() => void detail.refetch()} />}
            {detail.data && <OrganizationCard key={detail.data.id} resource={detail.data} />}
          </>}
      </section>
    </div>
  </OrganizationPage>;
}

function OrganizationCard({ resource }: { resource: Organization }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [auditOpen, setAuditOpen] = useState(false);
  const [draft, setDraft] = useState<{ name: string; description: string; base: Organization } | null>(null);
  const name = draft?.name ?? resource.name;
  const description = draft?.description ?? resource.description ?? "";
  const base = draft?.base ?? resource;
  const dirty = name !== base.name || description !== (base.description ?? "");
  const [archived, setArchived] = useState(false);
  const save = useMutation({
    mutationFn: () => updateResource("organization", resource.id, name.trim(), description || null),
    onSuccess: async updated => {
      client.setQueryData(["organization", resource.id], updated);
      setDraft(null);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["organizations"] }),
        client.invalidateQueries({ queryKey: ["entity-audit", "organizations", resource.id] }),
      ]);
    },
  });
  const archive = useMutation({ mutationFn: () => deleteOrganization(resource.id),
    onSuccess: async () => {
      setArchived(true);
      setDraft(null);
      await Promise.all([client.invalidateQueries({ queryKey: ["organizations"] }),
        client.invalidateQueries({ queryKey: ["projects"] })]);
      client.removeQueries({ queryKey: ["organization", resource.id] });
      navigate("/management/organizations", { state: { organizationArchived: true } });
    },
  });
  function change(field: "name" | "description", value: string) {
    save.reset();
    setDraft({ name, description, base, [field]: value });
  }
  return <>
    <UnsavedChanges dirty={dirty && !archived} />
    <header><h2>{resource.name}</h2>{resource.archived_at && <p className="readonly-note">Archived organization — read only.</p>}</header>
    <section className="organization-section" aria-label="Organization details">
      {resource.capabilities?.edit ? <form className="organization-form" onSubmit={event => {
        event.preventDefault();
        if (dirty && name.trim() && name.trim().length <= 200 && !save.isPending && !archive.isPending) save.mutate();
      }}>
        <label htmlFor="organization-name">Name</label>
        <input id="organization-name" required maxLength={200} value={name} disabled={save.isPending || archive.isPending} onChange={event => change("name", event.target.value)} />
        <label htmlFor="organization-description">Description</label>
        <textarea id="organization-description" rows={4} value={description} disabled={save.isPending || archive.isPending} onChange={event => change("description", event.target.value)} />
        <div className="organization-actions">
          <button className="button" disabled={!dirty || !name.trim() || name.trim().length > 200 || save.isPending || archive.isPending}>{save.isPending ? "Saving changes..." : "Save changes"}</button>
          <button type="button" className="button secondary" disabled={!dirty || save.isPending || archive.isPending} onClick={() => { setDraft(null); save.reset(); }}>Cancel changes</button>
        </div>
        {save.isError && <RequestError error={save.error} />}
        {save.isSuccess && <p role="status">Changes saved.</p>}
      </form> : <dl className="organization-readonly"><dt>Name</dt><dd>{resource.name}</dd><dt>Description</dt><dd>{resource.description || "No description provided."}</dd></dl>}
    </section>
    <section className="organization-section"><h3>Members</h3><Link className="button secondary" to={`/organizations/${resource.id}/members`}>{resource.capabilities?.manage_members ? "Manage members" : "View members"}</Link></section>
    {resource.capabilities?.view_audit && <details className="organization-section" open={auditOpen} onToggle={event => setAuditOpen(event.currentTarget.open)}>
      <summary>Administrative audit</summary>
      {auditOpen && <EntityAudit scope="organizations" id={resource.id} presentation="organization" />}
    </details>}
    <details className="organization-section"><summary>Technical details</summary><dl><dt>Identifier</dt><dd>{resource.id}</dd></dl></details>
    {resource.capabilities?.archive && <section className="organization-section organization-danger"><h3>Archive organization</h3>
      <p>{archiveConsequences}</p>
      <button className="button danger" disabled={archive.isPending || save.isPending} onClick={() => {
        if (window.confirm(`Archive “${resource.name}”? ${archiveConsequences}${dirty ? " Unsaved changes will be discarded." : ""}`)) archive.mutate();
      }}>{archive.isPending ? "Archiving organization..." : "Archive organization"}</button>
      {archive.isError && <RequestError error={archive.error} />}
    </section>}
  </>;
}

export function CreateOrganizationPage({ user }: { user: AuthUser }) {
  return <OrganizationPage title="Create organization">
    <Link className="button secondary" to="/management/organizations">Back to organizations</Link>
    {user.is_system_admin ? <CreateOrganizationForm /> : <p role="alert">Organization creation requires system administrator permissions.</p>}
  </OrganizationPage>;
}

function CreateOrganizationForm() {
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const create = useMutation({ mutationFn: () => createOrganization(name.trim(), description || null),
    onSuccess: async organization => {
      client.setQueryData(["organization", organization.id], organization);
      await client.invalidateQueries({ queryKey: ["organizations"] });
    },
  });
  if (create.isSuccess) return <Navigate replace to={`/management/organizations/${create.data.id}`} />;
  return <form className="organization-form organization-create" onSubmit={event => {
    event.preventDefault(); if (name.trim() && name.trim().length <= 200 && !create.isPending) create.mutate();
  }}>
    <UnsavedChanges dirty={Boolean(name || description) && !create.data} />
    <label htmlFor="organization-name">Name</label>
    <input id="organization-name" value={name} onChange={event => setName(event.target.value)} required maxLength={200} disabled={create.isPending} />
    <label htmlFor="organization-description">Description</label>
    <textarea id="organization-description" rows={4} value={description} onChange={event => setDescription(event.target.value)} disabled={create.isPending} />
    <div className="organization-actions"><button className="button" disabled={!name.trim() || create.isPending}>{create.isPending ? "Creating organization..." : "Create organization"}</button></div>
    {create.isError && <RequestError error={create.error} />}
  </form>;
}
