import { FormEvent, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  getProject,
  listOrganizations,
  listProjects,
  listMemberships,
  putMembership,
  removeMembership,
  listUsers,
  type Membership,
  type AuthUser,
  type Organization,
  type Project,
} from "./api";

type Props = {
  user: AuthUser;
  organizations: Organization[];
  projects: Project[];
  organizationId: string;
  projectId: string;
  loading: boolean;
  error: string;
  onOrganizationChange: (id: string) => void;
  onProjectChange: (id: string) => void;
  onClose: () => void;
  onProjectUpdated: (project: Project) => void;
};

export function MembersPage(props: Props) {
  const [section, setSection] = useState<"organization" | "project">(
    props.projectId ? "project" : "organization",
  );
  const organization = props.organizations.find(
    (item) => item.id === props.organizationId,
  );
  const project = props.projects.find(
    (item) =>
      item.id === props.projectId &&
      item.organization_id === props.organizationId,
  );
  const resource = section === "organization" ? organization : project;
  return (
    <main className="workspace-shell">
      <header className="workspace-header">
        <div>
          <div className="eyebrow">FreeSelfTrack</div>
          <h1>Members</h1>
        </div>
        <div className="workspace-actions">
          <button
            className="button secondary compact"
            type="button"
            onClick={props.onClose}
          >
            Back to workspace
          </button>
        </div>
      </header>
      <div className="members-context">
        <div>
          <label htmlFor="members-organization">Organization</label>
          <select
            id="members-organization"
            value={props.organizationId}
            onChange={(event) => props.onOrganizationChange(event.target.value)}
          >
            <option value="">No organization selected</option>
            {props.organizations.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="members-project">Project</label>
          <select
            id="members-project"
            value={project?.id ?? ""}
            disabled={props.loading || !props.projects.length}
            onChange={(event) => props.onProjectChange(event.target.value)}
          >
            <option value="">No project selected</option>
            {props.projects.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      {props.loading && <p role="status">Loading resources...</p>}
      {props.error && (
        <p className="error" role="alert">
          {props.error}
        </p>
      )}
      <nav className="mode-switch" aria-label="Member scope">
        <button
          className={section === "organization" ? "tab active" : "tab"}
          aria-pressed={section === "organization"}
          onClick={() => setSection("organization")}
        >
          Organization members
        </button>
        <button
          className={section === "project" ? "tab active" : "tab"}
          aria-pressed={section === "project"}
          onClick={() => setSection("project")}
        >
          Project members
        </button>
      </nav>
      {resource ? (
        <MemberList
          key={section + resource.id}
          scope={section}
          resource={resource}
          user={props.user}
          onProjectUpdated={props.onProjectUpdated}
        />
      ) : (
        <p className="empty-state">
          {section === "organization"
            ? "No organization selected."
            : "No project selected."}
        </p>
      )}
    </main>
  );
}

function MemberList({ scope, resource }: {
  scope: "organization" | "project"; resource: Organization | Project;
  user: AuthUser; onProjectUpdated: (project: Project) => void;
}) {
  const client = useQueryClient();
  const canManage = resource.capabilities?.manage_members ?? false;
  const canManageRoles = resource.capabilities?.manage_managers ?? false;
  const members = useInfiniteQuery({
    queryKey: [scope + "-membership-pages", resource.id], initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => listMemberships(scope, resource.id, pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined,
  });
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState("");
  const [role, setRole] = useState<Membership["role"]>("member");
  const [notice, setNotice] = useState("");
  const candidates = useInfiniteQuery({
    queryKey: ["member-candidates", scope, resource.id, search],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam }) => scope === "project"
      ? listMemberships("organization", (resource as Project).organization_id, pageParam).then(page => ({
          items: page.items.map(item => item.user), next_cursor: page.next_cursor,
        }))
      : listUsers(search, "active", pageParam),
    getNextPageParam: page => page.next_cursor ?? undefined, enabled: canManage,
  });
  const change = useMutation({
    mutationFn: async ({ id, role }: { id: string; role: Membership["role"] | null }) => {
      if (role === null) await removeMembership(scope, resource.id, id);
      else await putMembership(scope, resource.id, id, role);
    },
    onMutate: () => setNotice(""),
    onSuccess: async () => {
      setSelected(""); setNotice("Membership confirmed.");
      await client.invalidateQueries();
    },
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    if (selected && canManage && !change.isPending) change.mutate({ id: selected, role });
  }
  return <section className="members-content" aria-labelledby="member-list-title">
    <h2 id="member-list-title">{resource.name}</h2>
    {members.isPending && <p role="status">Loading members...</p>}
    {members.isError && <div><p role="alert">{members.error.message}</p>
      <button onClick={() => void members.refetch()}>Retry</button></div>}
    {members.isSuccess && <>
      <ul className="members-directory">{members.data.pages.flatMap(page => page.items).map(member =>
        <li className="member-row" key={member.user.id}>
          <span>{member.user.first_name} {member.user.last_name}</span>
          <span>{member.role === "manager" ? "Manager" : "Member"} · {member.state}</span>
          {canManageRoles && <button disabled={change.isPending} onClick={() => change.mutate({
            id: member.user.id, role: member.role === "manager" ? "member" : "manager",
          })}>{member.role === "manager" ? "Remove manager role" : "Make manager"}</button>}
          {canManage && <button disabled={change.isPending} onClick={() => {
            if (window.confirm(`Remove ${member.user.first_name} ${member.user.last_name} from ${resource.name}?`))
              change.mutate({ id: member.user.id, role: null });
          }}>Remove</button>}
        </li>)}</ul>
      {!members.data.pages[0].items.length && <p>No members found.</p>}
      {members.hasNextPage && <button disabled={members.isFetchingNextPage} onClick={() => void members.fetchNextPage()}>More members</button>}
    </>}
    {canManage && <form className="member-add-form" onSubmit={submit}>
      <h3>Add member</h3>
      {scope === "organization" && <><label htmlFor="member-search">Search users</label>
        <input id="member-search" value={search} onChange={event => { setSearch(event.target.value); setSelected(""); }} /></>}
      <label htmlFor="member-user">User</label>
      <select id="member-user" required value={selected} disabled={change.isPending} onChange={event => setSelected(event.target.value)}>
        <option value="">Select a user</option>
        {candidates.data?.pages.flatMap(page => page.items).map(user => <option key={user.id} value={user.id}>{user.first_name} {user.last_name}</option>)}
      </select>
      {candidates.isPending && <p role="status">Loading users...</p>}
      {candidates.isError && <p role="alert">{candidates.error.message}</p>}
      {candidates.hasNextPage && <button type="button" disabled={candidates.isFetchingNextPage} onClick={() => void candidates.fetchNextPage()}>More users</button>}
      {canManageRoles && <><label htmlFor="member-role">Role</label><select id="member-role" value={role} disabled={change.isPending} onChange={event => setRole(event.target.value as Membership["role"])}>
        <option value="member">Member</option><option value="manager">Manager</option></select></>}
      <button className="button compact" disabled={change.isPending || !selected}>{change.isPending ? "Saving..." : "Add member"}</button>
    </form>}
    {change.isError && <p role="alert">{change.error.message}</p>}
    {notice && <p role="status">{notice}</p>}
  </section>;
}

export function MembersRoutePage({
  user,
  scope,
}: {
  user: AuthUser;
  scope: "organization" | "project";
}) {
  const navigate = useNavigate();
  const { organizationId = "", projectId = "" } = useParams();
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    enabled: scope === "project",
    retry: false,
  });
  const activeOrganizationId =
    scope === "organization"
      ? organizationId
      : (project.data?.organization_id ?? "");
  const projects = useQuery({
    queryKey: ["projects", activeOrganizationId],
    queryFn: () => listProjects(activeOrganizationId),
    enabled: Boolean(activeOrganizationId),
  });
  const loading =
    organizations.isPending ||
    (scope === "project" && project.isPending) ||
    projects.isPending;
  const error = organizations.error || project.error || projects.error;
  return (
    <MembersPage
      key={`${scope}:${organizationId}:${projectId}`}
      user={user}
      organizations={organizations.data ?? []}
      projects={projects.data ?? []}
      organizationId={activeOrganizationId}
      projectId={scope === "project" ? projectId : ""}
      loading={loading}
      error={error instanceof Error ? error.message : ""}
      onOrganizationChange={(id) => navigate(`/organizations/${id}/members`)}
      onProjectChange={(id) => navigate(`/projects/${id}/members`)}
      onClose={() =>
        navigate(
          scope === "project" && projectId
            ? `/projects/${projectId}/kanban`
            : "/management/organizations",
        )
      }
      onProjectUpdated={(saved) => {
        void project.refetch();
        navigate(`/projects/${saved.id}/members`);
      }}
    />
  );
}
