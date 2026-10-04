import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Archive,
  Bell,
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Columns3,
  FolderKanban,
  LogOut,
  Plus,
  RotateCcw,
  Settings,
  Users,
  UserRound,
} from "lucide-react";
import {
  Link,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";

import {
  archiveStatus,
  createOrganization,
  createProject,
  createTaskLink,
  createStatus,
  deleteOrganization,
  deleteProject,
  getMyProfile,
  getProject,
  getTask,
  getUnreadNotificationCount,
  listArchivedStatuses,
  listNotifications,
  listOrganizations,
  listProjectMembers,
  listProjects,
  listStatuses,
  openNotification,
  reorderStatuses,
  restoreStatus,
  updateMyProfile,
  updateStatus,
  type AuthUser,
  type Organization,
  type Profile,
  type Status,
} from "./api";
import { KanbanView, NotificationTaskPanel } from "./KanbanView";
import { MembersRoutePage } from "./MembersPage";
import { AccountSecurity } from "./AccountSecurity";
import type { LinkSelection } from "./TaskLinks";

type Props = {
  user: AuthUser;
  onSignOut: () => void;
  onUserSaved: (profile: Profile) => void;
};

export function AuthenticatedApp(props: Props) {
  const [linkSelection, setLinkSelection] = useState<LinkSelection | null>(null);
  const kanban = (
    <KanbanPage
      user={props.user}
      linkSelection={linkSelection}
      onLinkSelection={setLinkSelection}
    />
  );
  return (
    <Routes>
      <Route element={<AuthenticatedLayout {...props} />}>
        <Route index element={<RootRedirect />} />
        <Route
          path="management/organizations"
          element={<OrganizationManagementPage user={props.user} />}
        />
        <Route
          path="management/organizations/:organizationId"
          element={<OrganizationManagementPage user={props.user} />}
        />
        <Route
          path="management/projects"
          element={<ProjectManagementPage user={props.user} />}
        />
        <Route
          path="management/projects/:projectId"
          element={<ProjectManagementPage user={props.user} />}
        />
        <Route
          path="management/projects/:projectId/workflow"
          element={<WorkflowManagementPage user={props.user} />}
        />
        <Route
          path="organizations/:organizationId/members"
          element={<MembersRoutePage user={props.user} scope="organization" />}
        />
        <Route
          path="projects/:projectId/members"
          element={<MembersRoutePage user={props.user} scope="project" />}
        />
        <Route
          path="projects/:projectId/kanban"
          element={kanban}
        />
        <Route
          path="projects/:projectId/kanban/tasks/:taskId"
          element={kanban}
        />
        <Route path="notifications" element={<NotificationsPage />} />
        <Route
          path="profile"
          element={
            <ProfilePage user={props.user} onSaved={props.onUserSaved} />
          }
        />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}

function AuthenticatedLayout({ user, onSignOut }: Props) {
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem("freeselftrack.sidebar.collapsed") === "true",
  );
  useEffect(() => {
    localStorage.setItem("freeselftrack.sidebar.collapsed", String(collapsed));
  }, [collapsed]);
  return (
    <div className={collapsed ? "app-layout sidebar-collapsed" : "app-layout"}>
      <AppSidebar
        user={user}
        collapsed={collapsed}
        onCollapse={() => setCollapsed((value) => !value)}
        onSignOut={onSignOut}
      />
      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}

function AppSidebar({
  user,
  collapsed,
  onCollapse,
  onSignOut,
}: {
  user: AuthUser;
  collapsed: boolean;
  onCollapse: () => void;
  onSignOut: () => void;
}) {
  const location = useLocation();
  const projectMatch = location.pathname.match(/(?:projects)\/([^/]+)/);
  const organizationMatch = location.pathname.match(/organizations\/([^/]+)/);
  const activeProjectId = projectMatch?.[1] ?? "";
  const project = useQuery({
    queryKey: ["project", activeProjectId],
    queryFn: () => getProject(activeProjectId),
    enabled: Boolean(activeProjectId),
    retry: false,
  });
  const activeOrganizationId =
    organizationMatch?.[1] ?? project.data?.organization_id ?? "";
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const unread = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: getUnreadNotificationCount,
    refetchInterval: 5000,
  });
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [flyout, setFlyout] = useState<string | null>(null);
  const asideRef = useRef<HTMLElement>(null);
  const flyoutTriggerRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (activeOrganizationId)
      setExpanded((current) => new Set(current).add(activeOrganizationId));
  }, [activeOrganizationId]);
  useEffect(() => {
    const outside = (event: MouseEvent) => {
      if (!asideRef.current?.contains(event.target as Node)) setFlyout(null);
    };
    const escape = (event: KeyboardEvent) => {
      if (event.key === "Escape" && flyout) {
        setFlyout(null);
        flyoutTriggerRef.current?.focus();
      }
    };
    document.addEventListener("mousedown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("mousedown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [flyout]);

  const closeFlyout = () => setFlyout(null);
  return (
    <aside
      className="app-sidebar"
      ref={asideRef}
      aria-label="Workspace navigation"
    >
      <div className="sidebar-top">
        <Link className="sidebar-brand" to="/">
          <Columns3 size={20} />
          <span>FreeSelfTrack</span>
        </Link>
        <button
          className="sidebar-icon-button"
          type="button"
          onClick={onCollapse}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
      <nav className="sidebar-nav">
        <SidebarLink
          to="/profile"
          icon={<UserRound size={18} />}
          label={
            user.profile
              ? `${user.profile.first_name} ${user.profile.last_name}`
              : user.email
          }
          collapsed={collapsed}
        />
        <SidebarLink
          to="/notifications"
          icon={<Bell size={18} />}
          label="Notifications"
          count={unread.data}
          collapsed={collapsed}
        />
        {activeProjectId ? (
          <SidebarLink
            to={`/projects/${activeProjectId}/members`}
            icon={<Users size={18} />}
            label="Members"
            collapsed={collapsed}
          />
        ) : activeOrganizationId ? (
          <SidebarLink
            to={`/organizations/${activeOrganizationId}/members`}
            icon={<Users size={18} />}
            label="Members"
            collapsed={collapsed}
          />
        ) : null}
        <div className="sidebar-divider" />
        <SidebarLink
          to="/management/organizations"
          icon={<Building2 size={18} />}
          label="Organizations"
          collapsed={collapsed}
        />
        <SidebarLink
          to={
            activeProjectId
              ? `/management/projects/${activeProjectId}`
              : "/management/projects"
          }
          icon={<Settings size={18} />}
          label="Project management"
          collapsed={collapsed}
        />
        {activeProjectId && (
          <SidebarLink
            to={`/management/projects/${activeProjectId}/workflow`}
            icon={<Columns3 size={18} />}
            label="Workflow"
            collapsed={collapsed}
          />
        )}
        <div className="sidebar-divider" />
        {organizations.isPending && (
          <span className="sidebar-state">
            {collapsed ? "..." : "Loading organizations..."}
          </span>
        )}
        {organizations.isError && (
          <button
            className="sidebar-state sidebar-retry"
            onClick={() => void organizations.refetch()}
          >
            {collapsed ? "!" : "Retry organizations"}
          </button>
        )}
        {organizations.data?.map((organization) => (
          <OrganizationBranch
            key={organization.id}
            organization={organization}
            collapsed={collapsed}
            expanded={expanded.has(organization.id)}
            flyoutOpen={flyout === organization.id}
            activeProjectId={activeProjectId}
            onToggle={(trigger) => {
              if (collapsed) {
                flyoutTriggerRef.current = trigger;
                setFlyout((current) =>
                  current === organization.id ? null : organization.id,
                );
              } else
                setExpanded((current) => {
                  const next = new Set(current);
                  if (next.has(organization.id)) next.delete(organization.id);
                  else next.add(organization.id);
                  return next;
                });
            }}
            onCloseFlyout={closeFlyout}
          />
        ))}
        {organizations.data?.length === 0 && (
          <span className="sidebar-state">
            {collapsed ? "0" : "No organizations"}
          </span>
        )}
      </nav>
      <button
        className="sidebar-link sidebar-logout"
        type="button"
        onClick={onSignOut}
        title="Sign out"
      >
        <LogOut size={18} />
        <span>Sign out</span>
      </button>
    </aside>
  );
}

function SidebarLink({
  to,
  icon,
  label,
  collapsed,
  count,
}: {
  to: string;
  icon: React.ReactNode;
  label: string;
  collapsed: boolean;
  count?: number;
}) {
  const location = useLocation();
  const active =
    location.pathname === to ||
    (to !== "/" && location.pathname.startsWith(to + "/"));
  return (
    <Link
      className={active ? "sidebar-link active" : "sidebar-link"}
      to={to}
      title={collapsed ? label : undefined}
      aria-current={active ? "page" : undefined}
    >
      {icon}
      <span>{label}</span>
      {Boolean(count) && <b className="sidebar-count">{count}</b>}
    </Link>
  );
}

function OrganizationBranch({
  organization,
  collapsed,
  expanded,
  flyoutOpen,
  activeProjectId,
  onToggle,
  onCloseFlyout,
}: {
  organization: Organization;
  collapsed: boolean;
  expanded: boolean;
  flyoutOpen: boolean;
  activeProjectId: string;
  onToggle: (trigger: HTMLButtonElement) => void;
  onCloseFlyout: () => void;
}) {
  const open = collapsed ? flyoutOpen : expanded;
  const projects = useQuery({
    queryKey: ["projects", organization.id],
    queryFn: () => listProjects(organization.id),
    enabled: open,
    retry: false,
  });
  return (
    <div
      className="organization-branch"
      onMouseLeave={() => collapsed && onCloseFlyout()}
    >
      <button
        className="sidebar-link organization-trigger"
        type="button"
        onClick={(event) => onToggle(event.currentTarget)}
        aria-expanded={open}
        title={collapsed ? organization.name : undefined}
      >
        <FolderKanban size={18} />
        <span>{organization.name}</span>
        {!collapsed && (
          <ChevronDown className={expanded ? "rotated" : ""} size={15} />
        )}
      </button>
      {open && (
        <div
          className={collapsed ? "project-tree sidebar-flyout" : "project-tree"}
          role={collapsed ? "menu" : undefined}
        >
          {collapsed && <strong>{organization.name}</strong>}
          {projects.isPending && (
            <span className="sidebar-state">Loading projects...</span>
          )}
          {projects.isError && (
            <button
              className="sidebar-state sidebar-retry"
              onClick={() => void projects.refetch()}
            >
              Retry projects
            </button>
          )}
          {projects.data?.map((project) => (
            <Link
              key={project.id}
              className={
                project.id === activeProjectId
                  ? "project-link active"
                  : "project-link"
              }
              to={`/projects/${project.id}/kanban`}
              onClick={onCloseFlyout}
            >
              {project.name}
            </Link>
          ))}
          {projects.data?.length === 0 && (
            <span className="sidebar-state">No projects</span>
          )}
        </div>
      )}
    </div>
  );
}

function RootRedirect() {
  const resources = useQuery({
    queryKey: ["route-bootstrap"],
    queryFn: async () => {
      const organizations = await listOrganizations();
      for (const organization of organizations) {
        const projects = await listProjects(organization.id);
        if (projects[0]) return projects[0].id;
      }
      return null;
    },
    retry: false,
  });
  if (resources.isPending) return <PageState>Loading workspace...</PageState>;
  if (resources.isError)
    return (
      <PageError
        error={resources.error}
        retry={() => void resources.refetch()}
      />
    );
  return (
    <Navigate
      replace
      to={
        resources.data
          ? `/projects/${resources.data}/kanban`
          : "/management/organizations"
      }
    />
  );
}

function OrganizationManagementPage({ user }: { user: AuthUser }) {
  const { organizationId } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const selected = organizations.data?.find(
    (item) => item.id === organizationId,
  );
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createOrganization(name.trim()),
    onSuccess: async (organization) => {
      setName("");
      await client.invalidateQueries({ queryKey: ["organizations"] });
      navigate(`/management/organizations/${organization.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: (organization: Organization) =>
      deleteOrganization(organization.id),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["organizations"] });
      navigate("/management/organizations");
    },
  });
  if (organizations.isPending)
    return <PageState>Loading organizations...</PageState>;
  if (organizations.isError)
    return (
      <PageError
        error={organizations.error}
        retry={() => void organizations.refetch()}
      />
    );
  return (
    <Page title="Organizations" eyebrow="Management">
      <div className="management-grid">
        <section className="management-list">
          <h2>Available organizations</h2>
          {organizations.data.map((organization) => (
            <Link
              className={
                organization.id === organizationId
                  ? "management-item active"
                  : "management-item"
              }
              key={organization.id}
              to={`/management/organizations/${organization.id}`}
            >
              {organization.name}
            </Link>
          ))}
          {!organizations.data.length && (
            <p className="muted">No organizations yet.</p>
          )}
        </section>
        <section className="management-detail">
          {organizationId && !selected ? (
            <NotFoundResource label="Organization" />
          ) : selected ? (
            <>
              <div className="content-heading">
                <div>
                  <div className="eyebrow">Organization</div>
                  <h2>{selected.name}</h2>
                </div>
              </div>
              <dl className="resource-facts">
                <dt>Identifier</dt>
                <dd>{selected.id}</dd>
                <dt>Owner</dt>
                <dd>{selected.owner_id}</dd>
              </dl>
              <Link
                className="text-link"
                to={`/organizations/${selected.id}/members`}
              >
                Manage members
              </Link>
              {selected.owner_id === user.id ? (
                <button
                  className="button danger compact"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (
                      window.confirm(
                        `Delete ${selected.name} and all its projects? You can restore them later.`,
                      )
                    )
                      remove.mutate(selected);
                  }}
                >
                  Delete organization
                </button>
              ) : (
                <p className="readonly-note">
                  Only the organization owner can change this organization.
                </p>
              )}
              {remove.isError && <InlineError error={remove.error} />}
            </>
          ) : (
            <p className="muted">Select an organization to view details.</p>
          )}
        </section>
      </div>
      <form
        className="management-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (name.trim()) create.mutate();
        }}
      >
        <h2>Create organization</h2>
        <label htmlFor="organization-name">Name</label>
        <input
          id="organization-name"
          value={name}
          onChange={(event) => setName(event.target.value)}
          required
        />
        <button className="button compact" disabled={create.isPending}>
          <Plus size={16} /> Create organization
        </button>
        {create.isError && <InlineError error={create.error} />}
      </form>
    </Page>
  );
}

function ProjectManagementPage({ user }: { user: AuthUser }) {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const organizations = useQuery({
    queryKey: ["organizations"],
    queryFn: listOrganizations,
  });
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId!),
    enabled: Boolean(projectId),
    retry: false,
  });
  const organizationId =
    project.data?.organization_id ??
    searchParams.get("organization") ??
    organizations.data?.[0]?.id ??
    "";
  const projects = useQuery({
    queryKey: ["projects", organizationId],
    queryFn: () => listProjects(organizationId),
    enabled: Boolean(organizationId),
  });
  const [name, setName] = useState("");
  const create = useMutation({
    mutationFn: () => createProject(organizationId, name.trim()),
    onSuccess: async (saved) => {
      setName("");
      await client.invalidateQueries({
        queryKey: ["projects", organizationId],
      });
      navigate(`/management/projects/${saved.id}`);
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteProject(projectId!),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: ["projects", organizationId],
      });
      navigate(`/management/projects?organization=${organizationId}`);
    },
  });
  return (
    <Page title="Projects" eyebrow="Management">
      <div className="management-toolbar">
        <label htmlFor="project-organization">Organization</label>
        <select
          id="project-organization"
          value={organizationId}
          onChange={(event) =>
            setSearchParams({ organization: event.target.value })
          }
        >
          {organizations.data?.map((organization) => (
            <option key={organization.id} value={organization.id}>
              {organization.name}
            </option>
          ))}
        </select>
      </div>
      <div className="management-grid">
        <section className="management-list">
          <h2>Projects</h2>
          {projects.isPending && <p>Loading projects...</p>}
          {projects.isError && <InlineError error={projects.error} />}
          {projects.data?.map((item) => (
            <Link
              className={
                item.id === projectId
                  ? "management-item active"
                  : "management-item"
              }
              key={item.id}
              to={`/management/projects/${item.id}`}
            >
              {item.name}
            </Link>
          ))}
          {projects.data?.length === 0 && (
            <p className="muted">No projects yet.</p>
          )}
        </section>
        <section className="management-detail">
          {projectId && project.isPending ? (
            <p>Loading project...</p>
          ) : project.isError ? (
            <NotFoundResource label="Project" />
          ) : project.data ? (
            <>
              <div className="content-heading">
                <div>
                  <div className="eyebrow">Project</div>
                  <h2>{project.data.name}</h2>
                </div>
              </div>
              <dl className="resource-facts">
                <dt>Identifier</dt>
                <dd>{project.data.id}</dd>
                <dt>Owner</dt>
                <dd>{project.data.owner_id}</dd>
              </dl>
              <div className="inline-actions">
                <Link
                  className="button-link"
                  to={`/projects/${project.data.id}/kanban`}
                >
                  Open Kanban
                </Link>
                <Link
                  className="button-link secondary"
                  to={`/management/projects/${project.data.id}/workflow`}
                >
                  Workflow
                </Link>
                <Link
                  className="button-link secondary"
                  to={`/projects/${project.data.id}/members`}
                >
                  Members
                </Link>
              </div>
              {project.data.owner_id === user.id ? (
                <button
                  className="button danger compact"
                  disabled={remove.isPending}
                  onClick={() => {
                    if (window.confirm(`Delete project ${project.data!.name}?`))
                      remove.mutate();
                  }}
                >
                  Delete project
                </button>
              ) : (
                <p className="readonly-note">
                  Project settings are read-only for members.
                </p>
              )}
              {remove.isError && <InlineError error={remove.error} />}
            </>
          ) : (
            <p className="muted">Select a project to view details.</p>
          )}
        </section>
      </div>
      {organizationId && (
        <form
          className="management-form"
          onSubmit={(event) => {
            event.preventDefault();
            if (name.trim()) create.mutate();
          }}
        >
          <h2>Create project</h2>
          <label htmlFor="project-name">Name</label>
          <input
            id="project-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
          <button className="button compact" disabled={create.isPending}>
            <Plus size={16} /> Create project
          </button>
          {create.isError && <InlineError error={create.error} />}
        </form>
      )}
    </Page>
  );
}

function WorkflowManagementPage({ user }: { user: AuthUser }) {
  const { projectId = "" } = useParams();
  const client = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    retry: false,
  });
  const statuses = useQuery({
    queryKey: ["statuses", projectId],
    queryFn: () => listStatuses(projectId),
    retry: false,
  });
  const archive = useQuery({
    queryKey: ["statuses", projectId, "archive"],
    queryFn: () => listArchivedStatuses(projectId),
    enabled: Boolean(project.data),
    retry: false,
  });
  const owner = project.data?.owner_id === user.id;
  const refresh = async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: ["statuses", projectId] }),
      client.invalidateQueries({
        queryKey: ["statuses", projectId, "archive"],
      }),
      client.invalidateQueries({ queryKey: ["board", projectId] }),
    ]);
  };
  const mutation = useMutation({
    mutationFn: async (action: () => Promise<unknown>) => action(),
    onSuccess: refresh,
  });
  const [name, setName] = useState("");
  const [dragged, setDragged] = useState<string | null>(null);
  const move = (statusId: string, direction: -1 | 1) => {
    if (!statuses.data || mutation.isPending) return;
    const ids = statuses.data.map((status) => status.id);
    const from = ids.indexOf(statusId);
    const to = from + direction;
    if (to < 0 || to >= ids.length) return;
    [ids[from], ids[to]] = [ids[to], ids[from]];
    mutation.mutate(() => reorderStatuses(projectId, ids));
  };
  if (project.isPending || statuses.isPending)
    return <PageState>Loading workflow...</PageState>;
  if (project.isError || statuses.isError || !project.data)
    return <NotFoundResource label="Project workflow" />;
  return (
    <Page title={`${project.data.name} workflow`} eyebrow="Workflow management">
      {!owner && (
        <p className="readonly-note">
          You can inspect this workflow. Only the project owner can change it.
        </p>
      )}
      {mutation.isError && <InlineError error={mutation.error} />}
      <section className="workflow-section">
        <div className="section-heading">
          <h2>Active columns</h2>
          <span>{statuses.data.length}</span>
        </div>
        <div className="workflow-list">
          {statuses.data.map((status, index) => (
            <WorkflowRow
              key={status.id}
              status={status}
              owner={owner}
              pending={mutation.isPending}
              draggable={owner}
              onDragStart={() => setDragged(status.id)}
              onDrop={() => {
                if (!dragged || dragged === status.id) return;
                const ids = statuses.data.map((item) => item.id);
                const from = ids.indexOf(dragged),
                  to = ids.indexOf(status.id);
                ids.splice(to, 0, ids.splice(from, 1)[0]);
                setDragged(null);
                mutation.mutate(() => reorderStatuses(projectId, ids));
              }}
              onRename={(next) =>
                mutation.mutate(() =>
                  updateStatus(projectId, status.id, { name: next }),
                )
              }
              onCompletion={(value) =>
                mutation.mutate(() =>
                  updateStatus(projectId, status.id, { is_completed: value }),
                )
              }
              onArchive={() =>
                mutation.mutate(() => archiveStatus(projectId, status.id))
              }
              onMove={(direction) => move(status.id, direction)}
              first={index === 0}
              last={index === statuses.data.length - 1}
            />
          ))}
        </div>
      </section>
      {owner && (
        <form
          className="workflow-create"
          onSubmit={(event) => {
            event.preventDefault();
            if (!name.trim()) return;
            mutation.mutate(() => createStatus(projectId, name.trim()), {
              onSuccess: () => setName(""),
            });
          }}
        >
          <label htmlFor="status-name">New column</label>
          <input
            id="status-name"
            value={name}
            onChange={(event) => setName(event.target.value)}
            required
          />
          <button className="button compact" disabled={mutation.isPending}>
            <Plus size={16} /> Add column
          </button>
        </form>
      )}
      <section className="workflow-section">
        <div className="section-heading">
          <h2>Archive</h2>
          <Archive size={18} />
        </div>
        {archive.isPending ? (
          <p>Loading archive...</p>
        ) : archive.isError ? (
          <InlineError error={archive.error} />
        ) : archive.data?.length ? (
          <div className="workflow-list">
            {archive.data.map((status) => (
              <div className="workflow-row archived" key={status.id}>
                <strong>{status.name}</strong>
                <button
                  className="icon-action"
                  title="Restore column"
                  aria-label={`Restore ${status.name}`}
                  onClick={() =>
                    mutation.mutate(() => restoreStatus(projectId, status.id))
                  }
                >
                  <RotateCcw size={16} />
                </button>
              </div>
            ))}
          </div>
        ) : (
          <p className="muted">Archive is empty.</p>
        )}
      </section>
    </Page>
  );
}

function WorkflowRow({
  status,
  owner,
  pending,
  draggable,
  onDragStart,
  onDrop,
  onRename,
  onCompletion,
  onArchive,
  onMove,
  first,
  last,
}: {
  status: Status;
  owner: boolean;
  pending: boolean;
  draggable: boolean;
  onDragStart: () => void;
  onDrop: () => void;
  onRename: (name: string) => void;
  onCompletion: (value: boolean) => void;
  onArchive: () => void;
  onMove: (direction: -1 | 1) => void;
  first: boolean;
  last: boolean;
}) {
  const [name, setName] = useState(status.name);
  useEffect(() => {
    if (!pending) setName(status.name);
  }, [pending, status.name]);
  return (
    <div
      className="workflow-row"
      draggable={draggable && !pending}
      onDragStart={onDragStart}
      onDragOver={(event) => owner && event.preventDefault()}
      onDrop={onDrop}
    >
      {owner ? (
        <input
          aria-label={`Name for ${status.name}`}
          value={name}
          onChange={(event) => setName(event.target.value)}
          onBlur={() => {
            if (name.trim() && name.trim() !== status.name)
              onRename(name.trim());
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") event.currentTarget.blur();
            if (event.key === "ArrowUp") {
              event.preventDefault();
              onMove(-1);
            }
            if (event.key === "ArrowDown") {
              event.preventDefault();
              onMove(1);
            }
          }}
          disabled={pending}
        />
      ) : (
        <strong>{status.name}</strong>
      )}
      <label className="workflow-completing">
        <input
          type="checkbox"
          checked={status.is_completed}
          onChange={(event) => onCompletion(event.target.checked)}
          disabled={!owner || pending}
        />{" "}
        Completing
      </label>
      {owner && (
        <div className="workflow-actions">
          <button
            className="icon-action"
            aria-label={`Move ${status.name} left`}
            title="Move left"
            disabled={first || pending}
            onClick={() => onMove(-1)}
          >
            <ChevronLeft size={16} />
          </button>
          <button
            className="icon-action"
            aria-label={`Move ${status.name} right`}
            title="Move right"
            disabled={last || pending}
            onClick={() => onMove(1)}
          >
            <ChevronRight size={16} />
          </button>
          <button
            className="icon-action danger-icon"
            aria-label={`Archive ${status.name}`}
            title="Archive column"
            disabled={pending}
            onClick={onArchive}
          >
            <Archive size={16} />
          </button>
        </div>
      )}
    </div>
  );
}

function KanbanPage({
  user,
  linkSelection,
  onLinkSelection,
}: {
  user: AuthUser;
  linkSelection: LinkSelection | null;
  onLinkSelection: (selection: LinkSelection | null) => void;
}) {
  const { projectId = "", taskId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const project = useQuery({
    queryKey: ["project", projectId],
    queryFn: () => getProject(projectId),
    retry: false,
  });
  const members = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => listProjectMembers(projectId),
    retry: false,
  });
  const createLink = useMutation({
    mutationFn: (targetTaskId: string) => {
      if (!linkSelection) throw new Error("Link selection is not active.");
      return createTaskLink(
        linkSelection.sourceTaskId,
        targetTaskId,
        linkSelection.relationType,
      );
    },
    onSuccess: async () => {
      if (!linkSelection) return;
      const source = linkSelection;
      onLinkSelection(null);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["task-links", source.sourceTaskId] }),
        client.invalidateQueries({ queryKey: ["task-history", source.sourceTaskId] }),
      ]);
      navigate(
        `/projects/${source.sourceProjectId}/kanban/tasks/${source.sourceTaskId}?tab=links`,
      );
    },
  });
  if (project.isPending) return <PageState>Loading Kanban...</PageState>;
  if (project.isError || !project.data)
    return <NotFoundResource label="Project" />;
  return (
    <Page title={project.data.name} eyebrow="Kanban">
      {createLink.isError && (
        <p className="error" role="alert">
          {createLink.error instanceof Error
            ? createLink.error.message
            : "Unable to create task link."}
        </p>
      )}
      <KanbanView
        project={project.data}
        currentUser={user}
        canWrite={members.isSuccess}
        linkSelection={
          linkSelection?.organizationId === project.data.organization_id
            ? linkSelection
            : null
        }
        onOpenTask={(id) =>
          navigate(`/projects/${projectId}/kanban/tasks/${id}`)
        }
        onOpenLinkedTask={(linkedProjectId, id) =>
          navigate(`/projects/${linkedProjectId}/kanban/tasks/${id}?tab=links`)
        }
        onStartLinkSelection={(selection) => {
          onLinkSelection(selection);
          navigate(`/projects/${projectId}/kanban`);
        }}
        onCancelLinkSelection={() => {
          createLink.reset();
          onLinkSelection(null);
        }}
        onSelectLinkedTask={(id) => createLink.mutate(id)}
      />
      {taskId && (
        <NotificationTaskPanel
          taskId={taskId}
          commentId={searchParams.get("comment") ?? undefined}
          initialActivity={
            searchParams.get("tab") === "links" ? "links" : "chat"
          }
          currentUser={user}
          onOpenLinkedTask={(linkedProjectId, id) =>
            navigate(`/projects/${linkedProjectId}/kanban/tasks/${id}?tab=links`)
          }
          onStartLinkSelection={(selection) => {
            onLinkSelection(selection);
            navigate(`/projects/${projectId}/kanban`);
          }}
          onClose={() => navigate(`/projects/${projectId}/kanban`)}
        />
      )}
    </Page>
  );
}

function NotificationsPage() {
  const navigate = useNavigate();
  const client = useQueryClient();
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: listNotifications,
    refetchInterval: 5000,
  });
  const open = useMutation({
    mutationFn: openNotification,
    onSuccess: async (notification) => {
      await Promise.all([
        client.invalidateQueries({ queryKey: ["notifications"] }),
        client.invalidateQueries({
          queryKey: ["notifications", "unread-count"],
        }),
      ]);
      if (!notification.task_id) return;
      const task = await getTask(notification.task_id);
      let commentId: string | undefined;
      let tab: string | undefined;
      try {
        const data = notification.event_data
          ? (JSON.parse(notification.event_data) as {
              comment_id?: string;
              tab?: string;
            })
          : null;
        commentId = data?.comment_id;
        tab = data?.tab;
      } catch {
        commentId = undefined;
        tab = undefined;
      }
      const params = new URLSearchParams();
      if (commentId) params.set("comment", commentId);
      if (tab === "links") params.set("tab", "links");
      navigate(
        `/projects/${task.project_id}/kanban/tasks/${task.id}${params.size ? `?${params}` : ""}`,
      );
    },
  });
  return (
    <Page title="Notifications" eyebrow="Inbox">
      {notifications.isPending ? (
        <p>Loading notifications...</p>
      ) : notifications.isError ? (
        <PageError
          error={notifications.error}
          retry={() => void notifications.refetch()}
        />
      ) : notifications.data.length ? (
        <div className="notifications-list">
          {notifications.data.map((notification) => (
            <button
              className={
                notification.read_at ? "notification read" : "notification"
              }
              key={notification.id}
              onClick={() => open.mutate(notification.id)}
              disabled={open.isPending}
            >
              <strong>{notification.message}</strong>
              <span>{new Date(notification.created_at).toLocaleString()}</span>
            </button>
          ))}
        </div>
      ) : (
        <p className="muted">No notifications.</p>
      )}
      {open.isError && <InlineError error={open.error} />}
    </Page>
  );
}

function ProfilePage({
  user,
  onSaved,
}: {
  user: AuthUser;
  onSaved: (profile: Profile) => void;
}) {
  const [firstName, setFirstName] = useState(user.profile?.first_name ?? "");
  const [lastName, setLastName] = useState(user.profile?.last_name ?? "");
  const profile = useQuery({ queryKey: ["profile"], queryFn: getMyProfile });
  useEffect(() => {
    if (profile.data) {
      setFirstName(profile.data.first_name);
      setLastName(profile.data.last_name);
    }
  }, [profile.data]);
  const save = useMutation({
    mutationFn: () => updateMyProfile(firstName, lastName),
    onSuccess: onSaved,
  });
  return (
    <Page title="Profile" eyebrow="Account">
      <form
        className="profile-form"
        onSubmit={(event) => {
          event.preventDefault();
          save.mutate();
        }}
      >
        <label htmlFor="profile-first-name">First name</label>
        <input
          id="profile-first-name"
          value={firstName}
          onChange={(event) => setFirstName(event.target.value)}
          required
        />
        <label htmlFor="profile-last-name">Last name</label>
        <input
          id="profile-last-name"
          value={lastName}
          onChange={(event) => setLastName(event.target.value)}
          required
        />
        <p className="muted">{user.email}</p>
        <button className="button compact" disabled={save.isPending}>
          Save profile
        </button>
        {profile.isError && <InlineError error={profile.error} />}
        {save.isError && <InlineError error={save.error} />}
        {save.isSuccess && <p className="notice">Profile saved.</p>}
      </form>
      <AccountSecurity />
    </Page>
  );
}

function Page({
  title,
  eyebrow,
  children,
}: {
  title: string;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <section className="route-page">
      <header className="route-header">
        <div className="eyebrow">{eyebrow}</div>
        <h1>{title}</h1>
      </header>
      {children}
    </section>
  );
}
function PageState({ children }: { children: React.ReactNode }) {
  return (
    <div className="route-state" role="status">
      {children}
    </div>
  );
}
function PageError({ error, retry }: { error: unknown; retry: () => void }) {
  return (
    <div className="route-state">
      <InlineError error={error} />
      <button className="button secondary compact" onClick={retry}>
        Retry
      </button>
    </div>
  );
}
function InlineError({ error }: { error: unknown }) {
  return (
    <p className="error" role="alert">
      {error instanceof Error ? error.message : "Request failed"}
    </p>
  );
}
function NotFoundResource({ label }: { label: string }) {
  return (
    <div className="route-state">
      <h2>{label} unavailable</h2>
      <p className="muted">
        It may have been removed or you may not have access.
      </p>
      <Link className="text-link" to="/management/organizations">
        Open available organizations
      </Link>
    </div>
  );
}
function NotFoundPage() {
  return <NotFoundResource label="Page" />;
}
