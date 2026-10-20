import { useEffect, useRef, useState, type ReactNode } from "react";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, useLocation, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { Plus } from "lucide-react";
import { ApiError, createProject, deleteProject, getOrganization, getProject, listMemberships, listOrganizations, listProjectPage, updateResource, type Organization, type Project } from "./api";
import { EntityAudit } from "./EntityAudit";
import { LifecycleDialog } from "./LifecycleDialog";
import { UnsavedChanges } from "./OrganizationManagementPage";

const archiveConsequences = "This archives the project and all its tasks. Memberships move to the archived state and access changes. Restoring does not automatically restore tasks or previous memberships and permissions.";
const catalogUrl = (id: string) => `/management/projects?organization=${encodeURIComponent(id)}`;
function ProjectPage({ title = "Projects", children }: { title?: string; children: ReactNode }) {
  return <section className="route-page project-management-page"><header className="route-header"><div className="eyebrow">Management</div><h1>{title}</h1></header>{children}</section>;
}
function accessDenied(error: Error | null) {
  return error instanceof ApiError && [401, 403, 404].includes(error.status);
}
function RequestError({ error, retry }: { error: Error; retry?: () => void }) {
  const unavailable = error instanceof ApiError && [403, 404].includes(error.status);
  return <div role="alert" className="error"><p>{unavailable ? "Resource unavailable or permission denied." : error.message}</p>{retry && <button className="button secondary" onClick={retry}>Retry</button>}</div>;
}
function OrganizationSelect({ organizations, id, onChange, disabled = false }: { organizations: Organization[]; id: string; onChange: (id: string) => void; disabled?: boolean }) {
  return <div className="project-organization"><label htmlFor="project-organization">Organization</label><select id="project-organization" value={id} disabled={disabled} onChange={event => onChange(event.target.value)}>
    {!organizations.some(org => org.id === id) && <option value={id}>{id ? "Selected organization" : "Choose organization"}</option>}
    {organizations.map(org => <option key={org.id} value={org.id}>{org.name}</option>)}
  </select></div>;
}

export function ProjectManagementPage() {
  const { projectId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const location = useLocation();
  const organizations = useQuery({ queryKey: ["organizations"], queryFn: listOrganizations });
  const project = useQuery({ queryKey: ["project", projectId], queryFn: () => getProject(projectId!), enabled: Boolean(projectId), retry: false });
  const organizationId = projectId ? project.data?.organization_id ?? "" : params.get("organization") ?? organizations.data?.[0]?.id ?? "";
  const organization = organizations.data?.find(item => item.id === organizationId);
  return <ProjectPage>
    <div className="project-toolbar">
      <OrganizationSelect organizations={organizations.data ?? []} id={organizationId} onChange={id => navigate(catalogUrl(id))} />
      {organizationId && <Link className="button secondary" to={`/archive?organization=${encodeURIComponent(organizationId)}`}>Archived projects</Link>}
      {organization?.capabilities?.create_project && <Link className="button secondary" to={`/management/projects/new?organization=${encodeURIComponent(organizationId)}`} state={{ from: location.pathname + location.search }}><Plus size={18} aria-hidden="true" />Create project</Link>}
    </div>
    {organizations.isPending && <p role="status">Loading organizations…</p>}
    {organizations.isError && <RequestError error={organizations.error} retry={() => void organizations.refetch()} />}
    {location.state?.projectArchived && <p role="status">Project archived.</p>}
    <div className="project-grid">
      <ProjectCatalog key={organizationId} organizationId={organizationId} selected={project.data} />
      <section className="project-detail" aria-label="Selected project">
        {!projectId ? <p>Select a project to view details.</p> : project.isPending ? <p role="status">Loading project…</p> : <>
          {project.isError && <RequestError error={project.error} retry={() => void project.refetch()} />}
          {project.data && !accessDenied(project.error) && <ProjectCard key={project.data.id} resource={project.data} organizationName={organization?.name} />}
        </>}
      </section>
    </div>
  </ProjectPage>;
}

function ProjectCatalog({ organizationId, selected }: { organizationId: string; selected?: Project }) {
  const projects = useInfiniteQuery({ queryKey: ["projects", organizationId, "pages"], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listProjectPage(organizationId, pageParam), getNextPageParam: page => page.next_cursor ?? undefined, enabled: Boolean(organizationId) });
  const [open, setOpen] = useState(false);
  const [wide, setWide] = useState(true);
  const picker = useRef<HTMLDetailsElement>(null);
  useEffect(() => {
    if (!window.matchMedia) return;
    const media = window.matchMedia("(min-width: 1100px)"); const update = () => setWide(media.matches);
    update(); media.addEventListener("change", update); return () => media.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    setOpen(false);
    if (picker.current?.contains(document.activeElement)) picker.current.querySelector("summary")?.focus();
  }, [selected?.id]);
  const items = projects.data?.pages.flatMap(page => page.items) ?? [];
  const visible = selected && selected.organization_id === organizationId && !items.some(item => item.id === selected.id) ? [selected, ...items] : items;
  return <details ref={picker} className="project-picker" open={wide || open} onToggle={event => { if (!wide) setOpen(event.currentTarget.open); }}>
    <summary>Choose project{selected ? `: ${selected.name}` : ""}</summary>
    <nav className="project-catalog" aria-label="Available projects"><h2>Projects</h2>
      {organizationId && projects.isPending && <p role="status">Loading projects…</p>}
      {projects.isError && <RequestError error={projects.error} retry={() => { if (projects.isFetchNextPageError) void projects.fetchNextPage(); else void projects.refetch(); }} />}
      {visible.map(item => <Link className={`management-item${item.id === selected?.id ? " active" : ""}`} aria-current={item.id === selected?.id ? "page" : undefined} key={item.id} to={`/management/projects/${item.id}`}>{item.name}</Link>)}
      {projects.isSuccess && !visible.length && <p>No projects yet.</p>}
      {!organizationId && <p>Choose an organization to see projects.</p>}
      {projects.hasNextPage && <button className="button secondary" disabled={projects.isFetchingNextPage} onClick={() => void projects.fetchNextPage()}>{projects.isFetchingNextPage ? "Loading projects…" : "Load more projects"}</button>}
    </nav>
  </details>;
}

function ProjectCard({ resource, organizationName }: { resource: Project; organizationName?: string }) {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<{ name: string; description: string; base: Project } | null>(null);
  const name = draft?.name ?? resource.name, description = draft?.description ?? resource.description ?? "", base = draft?.base ?? resource;
  const dirty = name !== base.name || description !== (base.description ?? "");
  const [confirmArchive, setConfirmArchive] = useState(false);
  const archiveTrigger = useRef<HTMLButtonElement>(null);
  const [archived, setArchived] = useState(false);
  const sending = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const canEdit = resource.capabilities?.edit && !resource.archived_at;
  const save = useMutation({ mutationFn: () => updateResource("project", resource.id, name.trim(), description || null), onSuccess: async updated => {
    client.setQueryData(["project", resource.id], { ...resource, ...updated });
    if (mounted.current) setDraft(null);
    await Promise.all([client.invalidateQueries({ queryKey: ["projects", resource.organization_id] }), client.invalidateQueries({ queryKey: ["entity-audit", "projects", resource.id] })]);
  }, onSettled: () => { sending.current = false; } });
  const archive = useMutation({ mutationFn: () => deleteProject(resource.id), onSuccess: async () => {
    if (mounted.current) { setArchived(true); setDraft(null); }
    await client.invalidateQueries({ queryKey: ["projects", resource.organization_id] });
    client.removeQueries({ queryKey: ["project", resource.id] });
    if (mounted.current) navigate(catalogUrl(resource.organization_id), { state: { projectArchived: true } });
  }, onSettled: () => { sending.current = false; } });
  function change(field: "name" | "description", value: string) { save.reset(); setDraft({ name, description, base, [field]: value }); }
  const busy = save.isPending || archive.isPending;
  return <>
    <UnsavedChanges dirty={dirty && !archived} />
    <header><h2>{resource.name}</h2>{organizationName && <p className="project-parent">{organizationName}</p>}
      {resource.archived_at && <p className="readonly-note">Archived project — read only.</p>}
    </header>
    <nav className="project-actions project-working-links" aria-label="Project pages">
      <Link className="button" to={`/projects/${resource.id}/kanban`}>Open Kanban</Link>
      <Link className="button secondary" to={`/management/projects/${resource.id}/workflow`}>Workflow</Link>
      <Link className="button secondary" to={`/projects/${resource.id}/members`}>Members</Link>
    </nav>
    <section className="project-section" aria-label="Project details"><h3>Project details</h3>
      {canEdit ? <form className="project-form" onSubmit={event => { event.preventDefault(); if (dirty && name.trim() && name.trim().length <= 200 && !sending.current) { sending.current = true; save.mutate(); } }}>
        <label htmlFor="project-name">Name</label><input id="project-name" required maxLength={200} value={name} disabled={busy} onChange={event => change("name", event.target.value)} />
        <label htmlFor="project-description">Description</label><textarea id="project-description" rows={3} value={description} disabled={busy} onChange={event => change("description", event.target.value)} />
        <div className="project-actions"><button className="button" disabled={!dirty || !name.trim() || name.trim().length > 200 || busy}>{save.isPending ? "Saving changes…" : "Save changes"}</button><button className="button secondary" type="button" disabled={!dirty || busy} onClick={() => { setDraft(null); save.reset(); }}>Cancel changes</button></div>
        {save.isError && <RequestError error={save.error} />}{save.isSuccess && <p role="status">Changes saved.</p>}
      </form> : <><p className="readonly-note">Project details are read-only.</p><dl><dt>Name</dt><dd>{resource.name}</dd><dt>Description</dt><dd>{resource.description || "No description provided."}</dd></dl></>}
    </section>
    {resource.capabilities?.view_audit && <ProjectHistory key={`${resource.id}:${resource.capabilities.view_audit}`} id={resource.id} />}
    <details className="project-section"><summary>Technical details</summary><dl><dt>Identifier</dt><dd>{resource.id}</dd></dl></details>
    {resource.capabilities?.archive && !resource.archived_at && <section className="project-section project-danger"><h3>Archive project</h3><p>{archiveConsequences}</p>
      <button ref={archiveTrigger} className="button danger" disabled={busy} onClick={() => { archive.reset(); setConfirmArchive(true); }}>Archive project</button>
    </section>}
    {confirmArchive && <LifecycleDialog returnFocus={archiveTrigger.current} title="Archive project?" onDismiss={() => { if (!sending.current) setConfirmArchive(false); }}>
      <h2>Archive project?</h2><p><strong>“{resource.name}”</strong></p><p>{archiveConsequences}</p>{dirty && <p>Unsaved changes will be discarded.</p>}
      {archive.isError && <RequestError error={archive.error} />}{archive.isPending && <p role="status">Archiving project…</p>}
      <div className="project-actions" onKeyDown={event => {
        if (event.key !== "Tab") return;
        const buttons = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>("button:not(:disabled)"));
        if (document.activeElement === (event.shiftKey ? buttons[0] : buttons.at(-1))) { event.preventDefault(); (event.shiftKey ? buttons.at(-1) : buttons[0])?.focus(); }
      }}><button autoFocus className="button secondary" aria-disabled={archive.isPending} onClick={() => { if (!sending.current) setConfirmArchive(false); }}>Cancel</button><button className="button danger" disabled={archive.isPending} onClick={() => { if (!sending.current) { sending.current = true; archive.mutate(); } }}>Archive project</button></div>
    </LifecycleDialog>}
  </>;
}

function ProjectHistory({ id }: { id: string }) {
  const [open, onOpen] = useState(false);
  return <details className="project-section project-history" open={open} onToggle={event => onOpen(event.currentTarget.open)}><summary>Change history</summary>{open && <EntityAudit scope="projects" id={id} presentation="project" />}</details>;
}

export function CreateProjectPage() {
  const [params] = useSearchParams(); const navigate = useNavigate(); const location = useLocation();
  const organizations = useQuery({ queryKey: ["organizations"], queryFn: listOrganizations });
  const id = params.get("organization") ?? organizations.data?.[0]?.id ?? "";
  const organization = useQuery({ queryKey: ["organization", id], queryFn: () => getOrganization(id), enabled: Boolean(id), retry: false });
  const available = organizations.data ?? [];
  const choices = organization.data && !available.some(org => org.id === id) ? [organization.data, ...available] : available;
  const from: unknown = location.state?.from;
  const back = typeof from === "string" && /^\/management\/projects(?:\?|\/[^/?]+(?:\?|$)|$)/.test(from) && !from.startsWith("/management/projects/new") ? from : catalogUrl(id);
  return <ProjectPage title="Create project">
    <div className="project-toolbar"><OrganizationSelect organizations={choices} id={id} onChange={next => navigate(`/management/projects/new?organization=${encodeURIComponent(next)}`)} /></div>
    {organizations.isError && <RequestError error={organizations.error} retry={() => void organizations.refetch()} />}
    {id && organization.isPending && <p role="status">Loading organization…</p>}
    {organization.isError && <RequestError error={organization.error} retry={() => void organization.refetch()} />}
    {organization.data && !accessDenied(organization.error) && (organization.data.capabilities?.create_project && !organization.data.archived_at ? <CreateProjectForm key={id} organization={organization.data} back={back} /> : <p role="alert">Project creation is not available in this organization.</p>)}
    {!id && !organizations.isPending && <p>No available organization. Project creation is unavailable.</p>}
    <Link className="button secondary" to={back}>Cancel</Link>
  </ProjectPage>;
}
function CreateProjectForm({ organization, back }: { organization: Organization; back: string }) {
  const client = useQueryClient(); const [name, setName] = useState(""); const [description, setDescription] = useState(""); const [managerIds, setManagerIds] = useState<string[]>([]);
  const sending = useRef(false);
  const create = useMutation({ mutationFn: () => createProject(organization.id, name.trim(), description || null, managerIds), onSuccess: async project => {
    client.setQueryData(["project", project.id], project);
    await client.invalidateQueries({ queryKey: ["projects", organization.id] });
  }, onSettled: () => { sending.current = false; } });
  if (create.isSuccess) return <Navigate replace to={`/management/projects/${create.data.id}`} state={{ from: back }} />;
  return <form className="project-form project-create" onSubmit={event => { event.preventDefault(); if (name.trim() && name.trim().length <= 200 && !sending.current) { sending.current = true; create.mutate(); } }}>
    <UnsavedChanges dirty={Boolean(name || description || managerIds.length) && !create.data} />
    <p>Creating in <strong>{organization.name}</strong></p>
    <label htmlFor="project-name">Name</label><input id="project-name" required maxLength={200} value={name} disabled={create.isPending} onChange={event => setName(event.target.value)} />
    <label htmlFor="project-description">Description</label><textarea id="project-description" rows={3} value={description} disabled={create.isPending} onChange={event => setDescription(event.target.value)} />
    <ManagerPicker organizationId={organization.id} selected={managerIds} onChange={setManagerIds} disabled={create.isPending} />
    <button className="button" disabled={!name.trim() || create.isPending}>{create.isPending ? "Creating project…" : "Create project"}</button>
    {create.isError && <RequestError error={create.error} />}
  </form>;
}
function ManagerPicker({ organizationId, selected, onChange, disabled }: { organizationId: string; selected: string[]; onChange: (ids: string[]) => void; disabled: boolean }) {
  const [cursor, setCursor] = useState<string>();
  const members = useQuery({ queryKey: ["manager-candidates", organizationId, cursor], queryFn: () => listMemberships("organization", organizationId, cursor) });
  return <fieldset disabled={disabled}><legend>Project managers (optional)</legend>
    {members.isPending && <p role="status">Loading candidates…</p>}{members.isError && <RequestError error={members.error} retry={() => void members.refetch()} />}
    {members.data?.items.map(({ user }) => <label className="project-candidate" key={user.id}><input type="checkbox" checked={selected.includes(user.id)} onChange={event => onChange(event.target.checked ? [...selected, user.id] : selected.filter(id => id !== user.id))} />{user.first_name} {user.last_name}</label>)}
    {members.data?.next_cursor && <button className="button secondary" type="button" disabled={members.isFetching} onClick={() => setCursor(members.data!.next_cursor!)}>More candidates</button>}
  </fieldset>;
}
