import { FormEvent, useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addProjectMember,
  createOrganization,
  createProject,
  getMyProfile,
  deleteProject,
  listOrganizations,
  listNotifications,
  listProjectMembers,
  listProjects,
  getUnreadNotificationCount,
  openNotification,
  login,
  register,
  updateMyProfile,
  removeProjectMember,
  transferProjectOwnership,
  type AuthUser,
  type Organization,
  type Project,
} from "./api";
import { KanbanView } from "./KanbanView";

type Mode = "login" | "register";

const savedToken = localStorage.getItem("freeselftrack.access_token");
const savedUser = localStorage.getItem("freeselftrack.user");

export function App() {
  const [mode, setMode] = useState<Mode>(savedToken ? "login" : "register");
  const [email, setEmail] = useState(savedUser ? JSON.parse(savedUser).email : "");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [profileOpen, setProfileOpen] = useState(false);
  const [user, setUser] = useState<AuthUser | null>(savedToken && savedUser ? JSON.parse(savedUser) : null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setSubmitting(true);

    try {
      if (mode === "register") {
        await register(email, password, firstName, lastName);
        setPassword("");
        setMode("login");
        setNotice("Account created. Sign in to continue.");
      } else {
        const response = await login(email, password);
        localStorage.setItem("freeselftrack.access_token", response.access_token);
        localStorage.setItem("freeselftrack.user", JSON.stringify(response.user));
        setUser(response.user);
        setPassword("");
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : "Request failed");
    } finally {
      setSubmitting(false);
    }
  }

  function signOut() {
    localStorage.removeItem("freeselftrack.access_token");
    localStorage.removeItem("freeselftrack.user");
    setUser(null);
    setMode("login");
    setNotice("");
  }

  if (user) {
    if (profileOpen) {
      return <ProfilePage user={user} onClose={() => setProfileOpen(false)} onSaved={(profile) => { const next = { ...user, profile }; setUser(next); localStorage.setItem("freeselftrack.user", JSON.stringify(next)); setProfileOpen(false); }} />;
    }
    return <Workspace user={user} onSignOut={signOut} onOpenProfile={() => setProfileOpen(true)} />;
  }

  return (
    <main className="shell">
      <section className="auth-panel" aria-labelledby="auth-title">
        <div className="eyebrow">FreeSelfTrack</div>
        <h1 id="auth-title">{mode === "register" ? "Create your account" : "Welcome back"}</h1>
        <p className="muted">
          {mode === "register"
            ? "Set up your account to start organizing work."
            : "Sign in to continue to your workspace."}
        </p>

        <div className="mode-switch" role="tablist" aria-label="Authentication mode">
          <button
            className={mode === "register" ? "tab active" : "tab"}
            type="button"
            role="tab"
            aria-selected={mode === "register"}
            onClick={() => {
              setMode("register");
              setError("");
              setNotice("");
            }}
          >
            Register
          </button>
          <button
            className={mode === "login" ? "tab active" : "tab"}
            type="button"
            role="tab"
            aria-selected={mode === "login"}
            onClick={() => {
              setMode("login");
              setError("");
              setNotice("");
            }}
          >
            Sign in
          </button>
        </div>

        <form onSubmit={handleSubmit} noValidate>
          {mode === "register" && <>
            <label htmlFor="first-name">First name</label>
            <input id="first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} required />
            <label htmlFor="last-name">Last name</label>
            <input id="last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} required />
          </>}

          <label htmlFor="email">Email</label>
          <input
            id="email"
            name="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />

          <label htmlFor="password">Password</label>
          <input
            id="password"
            name="password"
            type="password"
            autoComplete={mode === "register" ? "new-password" : "current-password"}
            minLength={mode === "register" ? 8 : 1}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />

          {notice && <p className="notice" role="status">{notice}</p>}
          {error && <p className="error" role="alert">{error}</p>}

          <button className="button" type="submit" disabled={submitting}>
            {submitting ? "Working..." : mode === "register" ? "Create account" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}

function ProfilePage({ user, onClose, onSaved }: { user: AuthUser; onClose: () => void; onSaved: (profile: NonNullable<AuthUser["profile"]>) => void }) {
  const [firstName, setFirstName] = useState(user.profile?.first_name ?? "");
  const [lastName, setLastName] = useState(user.profile?.last_name ?? "");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { void getMyProfile().then((profile) => { setFirstName(profile.first_name); setLastName(profile.last_name); }).catch((requestError) => setError(messageFor(requestError))); }, []);
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); setSaving(true); setError(""); try { onSaved(await updateMyProfile(firstName, lastName)); } catch (requestError) { setError(messageFor(requestError)); } finally { setSaving(false); } }
  return <main className="shell"><section className="workspace-panel" aria-labelledby="profile-title"><div className="workspace-header"><div><div className="eyebrow">Account</div><h1 id="profile-title">Profile</h1></div><button className="button secondary compact" type="button" onClick={onClose}>Back to workspace</button></div><form onSubmit={(event) => void submit(event)}><label htmlFor="profile-first-name">First name</label><input id="profile-first-name" value={firstName} onChange={(event) => setFirstName(event.target.value)} required /><label htmlFor="profile-last-name">Last name</label><input id="profile-last-name" value={lastName} onChange={(event) => setLastName(event.target.value)} required /><p className="muted">{user.email}</p>{error && <p className="error" role="alert">{error}</p>}<button className="button" type="submit" disabled={saving}>{saving ? "Saving..." : "Save profile"}</button></form></section></main>;
}

type WorkspaceProps = {
  user: AuthUser;
  onSignOut: () => void;
  onOpenProfile: () => void;
};

function Workspace({ user, onSignOut, onOpenProfile }: WorkspaceProps) {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<AuthUser[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [transferEmail, setTransferEmail] = useState("");
  const [organizationName, setOrganizationName] = useState("");
  const [projectName, setProjectName] = useState("");
  const [showOrganizationForm, setShowOrganizationForm] = useState(false);
  const [showProjectForm, setShowProjectForm] = useState(false);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");
  const [kanbanOpen, setKanbanOpen] = useState(false);

  const project = projects.find((item) => item.id === projectId) ?? null;
  const isOwner = project?.owner_id === user.id;

  useEffect(() => {
    void loadOrganizations();
  }, []);

  useEffect(() => {
    if (!organizationId) {
      setProjects([]);
      setProjectId("");
      return;
    }
    void loadProjects(organizationId);
  }, [organizationId]);

  useEffect(() => {
    if (projectId) {
      void loadMembers(projectId);
    } else {
      setMembers([]);
    }
  }, [projectId]);
  useEffect(() => { setKanbanOpen(false); }, [projectId]);

  async function loadOrganizations() {
    setLoading(true);
    setError("");
    try {
      const result = await listOrganizations();
      setOrganizations(result);
      setOrganizationId(result[0]?.id ?? "");
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setLoading(false);
    }
  }

  async function loadProjects(id: string) {
    setError("");
    try {
      const result = await listProjects(id);
      setProjects(result);
      setProjectId((current) => result.some((item) => item.id === current) ? current : result[0]?.id ?? "");
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  async function loadMembers(id: string) {
    setError("");
    try {
      setMembers(await listProjectMembers(id));
    } catch (requestError) {
      setError(messageFor(requestError));
    }
  }

  async function handleCreateOrganization(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organizationName.trim()) return;
    await perform(async () => {
      const created = await createOrganization(organizationName.trim());
      setOrganizations((current) => [...current, created]);
      setOrganizationId(created.id);
      setOrganizationName("");
      setShowOrganizationForm(false);
    });
  }

  async function handleCreateProject(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!organizationId || !projectName.trim()) return;
    await perform(async () => {
      const created = await createProject(organizationId, projectName.trim());
      setProjects((current) => [...current, created]);
      setProjectId(created.id);
      setProjectName("");
      setShowProjectForm(false);
    });
  }

  async function handleAddMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !memberEmail.trim()) return;
    await perform(async () => {
      await addProjectMember(projectId, memberEmail);
      setMemberEmail("");
      await loadMembers(projectId);
    });
  }

  async function handleRemoveMember(memberId: string) {
    if (!projectId) return;
    await perform(async () => {
      await removeProjectMember(projectId, memberId);
      await loadMembers(projectId);
    });
  }

  async function handleTransferOwnership(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!projectId || !transferEmail.trim()) return;
    await perform(async () => {
      const updated = await transferProjectOwnership(projectId, transferEmail);
      setProjects((current) => current.map((item) => item.id === updated.id ? updated : item));
      setTransferEmail("");
    });
  }

  async function handleDeleteProject() {
    if (!project || !window.confirm(`Delete project "${project.name}"? Its data will be kept as deleted.`)) return;
    await perform(async () => {
      await deleteProject(project.id);
      const remaining = projects.filter((item) => item.id !== project.id);
      setProjects(remaining);
      setProjectId(remaining[0]?.id ?? "");
    });
  }

  async function perform(operation: () => Promise<void>) {
    setWorking(true);
    setError("");
    try {
      await operation();
    } catch (requestError) {
      setError(messageFor(requestError));
    } finally {
      setWorking(false);
    }
  }

  return (
    <main className="workspace-shell">
      <header className="workspace-header">
        <div>
          <div className="eyebrow">FreeSelfTrack workspace</div>
          <h1>Projects and members</h1>
          <p className="muted">{user.email}</p>
        </div>
        <div className="workspace-actions">
          <NotificationCenter />
          <button className="button secondary compact" type="button" onClick={onOpenProfile}>Profile</button>
          <button className="button secondary compact" type="button" onClick={onSignOut}>Sign out</button>
        </div>
      </header>

      {error && <p className="error workspace-message" role="alert">{error}</p>}
      {loading ? <p className="loading">Loading organizations...</p> : (
        <div className="workspace-grid">
          <aside className="workspace-sidebar" aria-label="Projects navigation">
            <label htmlFor="organization">Organization</label>
            <select id="organization" value={organizationId} onChange={(event) => setOrganizationId(event.target.value)}>
              <option value="">No organizations</option>
              {organizations.map((organization) => <option key={organization.id} value={organization.id}>{organization.name}</option>)}
            </select>
            <button className="button secondary compact" type="button" onClick={() => setShowOrganizationForm((value) => !value)} disabled={working}>{showOrganizationForm ? "Cancel" : "New organization"}</button>
            {showOrganizationForm && <form onSubmit={(event) => void handleCreateOrganization(event)}>
              <label htmlFor="organization-name">Name</label>
              <input id="organization-name" value={organizationName} onChange={(event) => setOrganizationName(event.target.value)} required />
              <button className="button compact" type="submit" disabled={working}>Create organization</button>
            </form>}
            <label htmlFor="project">Project</label>
            <select id="project" value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={!projects.length}>
              <option value="">No projects</option>
              {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
            {organizationId && <button className="button secondary compact" type="button" onClick={() => setShowProjectForm((value) => !value)} disabled={working}>{showProjectForm ? "Cancel" : "New project"}</button>}
            {showProjectForm && organizationId && <form onSubmit={(event) => void handleCreateProject(event)}>
              <label htmlFor="project-name">Name</label>
              <input id="project-name" value={projectName} onChange={(event) => setProjectName(event.target.value)} required />
              <button className="button compact" type="submit" disabled={working}>Create project</button>
            </form>}
          </aside>

          <section className="workspace-content" aria-labelledby="members-title">
            {!project ? <div className="empty-state"><h2>No project selected</h2><p className="muted">Choose an organization and project to manage members.</p></div> : (
              <>
                <div className="content-heading">
                  <div><div className="eyebrow">Project</div><h2 id="members-title">{project.name}</h2></div>
                  {isOwner && <button className="button danger compact" type="button" onClick={() => void handleDeleteProject()} disabled={working}>Delete project</button>}
                </div>
                <button className="button compact" type="button" onClick={() => setKanbanOpen(true)}>Open Kanban</button>
                {kanbanOpen ? <KanbanView project={project} currentUser={user} onClose={() => setKanbanOpen(false)} /> : <>
                <div className="member-list">
                  <div className="section-heading"><h3>Members</h3><span>{members.length}</span></div>
                  {members.map((member) => <div className="member-row" key={member.id}><span>{member.email}</span>{member.id === project.owner_id ? <span className="role">Owner</span> : isOwner ? <button className="link-button" type="button" onClick={() => void handleRemoveMember(member.id)} disabled={working}>Remove</button> : null}</div>)}
                  {!members.length && <p className="muted">No members found.</p>}
                </div>
                {isOwner && <div className="forms-row">
                  <form onSubmit={handleAddMember}><h3>Add member</h3><label htmlFor="member-email">Email</label><input id="member-email" type="email" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} required /><button className="button" type="submit" disabled={working}>Add member</button></form>
                  <form onSubmit={handleTransferOwnership}><h3>Transfer ownership</h3><label htmlFor="transfer-email">Member email</label><input id="transfer-email" type="email" value={transferEmail} onChange={(event) => setTransferEmail(event.target.value)} required /><button className="button secondary" type="submit" disabled={working}>Transfer</button></form>
                </div>}
                </>}
              </>
            )}
          </section>
        </div>
      )}
    </main>
  );
}

function messageFor(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}


type NotificationCenterProps = {
  onOpenTask?: (taskId: string) => void;
};

export function NotificationCenter({ onOpenTask }: NotificationCenterProps) {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState(false);
  const notifications = useQuery({
    queryKey: ["notifications"],
    queryFn: listNotifications,
    enabled: expanded,
  });
  const unread = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: getUnreadNotificationCount,
    refetchInterval: 30_000,
  });
  const open = useMutation({
    mutationFn: openNotification,
    onSuccess: (notification) => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
      queryClient.invalidateQueries({ queryKey: ["notifications", "unread-count"] });
      if (notification.task_id) onOpenTask?.(notification.task_id);
    },
  });

  return (
    <div className="notification-center">
      <button
        className="button secondary compact"
        type="button"
        aria-expanded={expanded}
        onClick={() => setExpanded((value) => !value)}
      >
        Notifications{unread.data ? ` (${unread.data})` : ""}
      </button>
      {expanded && (
        <div className="notification-panel" role="dialog" aria-label="Notifications">
          {notifications.isPending && <p className="muted">Loading notifications...</p>}
          {notifications.isError && <p className="error">Unable to load notifications.</p>}
          {!notifications.isPending && !notifications.isError && !notifications.data.length && (
            <p className="muted">No notifications.</p>
          )}
          {open.isError && <p className="error" role="alert">Unable to open notification.</p>}
          {notifications.data?.map((notification) => (
            <button
              className={notification.read_at ? "notification read" : "notification"}
              type="button"
              key={notification.id}
              onClick={() => void open.mutateAsync(notification.id)}
              disabled={open.isPending}
            >
              <strong>{notification.message}</strong>
              <span>{new Date(notification.created_at).toLocaleString()}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
