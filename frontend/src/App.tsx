import { FormEvent, useEffect, useState } from "react";

import {
  addProjectMember,
  deleteProject,
  listOrganizations,
  listProjectMembers,
  listProjects,
  login,
  register,
  removeProjectMember,
  transferProjectOwnership,
  type AuthUser,
  type Organization,
  type Project,
} from "./api";

type Mode = "login" | "register";

const savedToken = localStorage.getItem("freeselftrack.access_token");
const savedUser = localStorage.getItem("freeselftrack.user");

export function App() {
  const [mode, setMode] = useState<Mode>(savedToken ? "login" : "register");
  const [email, setEmail] = useState(savedUser ? JSON.parse(savedUser).email : "");
  const [password, setPassword] = useState("");
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
        await register(email, password);
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
    return <Workspace user={user} onSignOut={signOut} />;
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

type WorkspaceProps = {
  user: AuthUser;
  onSignOut: () => void;
};

function Workspace({ user, onSignOut }: WorkspaceProps) {
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<AuthUser[]>([]);
  const [organizationId, setOrganizationId] = useState("");
  const [projectId, setProjectId] = useState("");
  const [memberEmail, setMemberEmail] = useState("");
  const [transferEmail, setTransferEmail] = useState("");
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
  const [error, setError] = useState("");

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
        <button className="button secondary compact" type="button" onClick={onSignOut}>Sign out</button>
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
            <label htmlFor="project">Project</label>
            <select id="project" value={projectId} onChange={(event) => setProjectId(event.target.value)} disabled={!projects.length}>
              <option value="">No projects</option>
              {projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </aside>

          <section className="workspace-content" aria-labelledby="members-title">
            {!project ? <div className="empty-state"><h2>No project selected</h2><p className="muted">Choose an organization and project to manage members.</p></div> : (
              <>
                <div className="content-heading">
                  <div><div className="eyebrow">Project</div><h2 id="members-title">{project.name}</h2></div>
                  {isOwner && <button className="button danger compact" type="button" onClick={() => void handleDeleteProject()} disabled={working}>Delete project</button>}
                </div>
                <div className="member-list">
                  <div className="section-heading"><h3>Members</h3><span>{members.length}</span></div>
                  {members.map((member) => <div className="member-row" key={member.id}><span>{member.email}</span>{member.id === project.owner_id ? <span className="role">Owner</span> : isOwner ? <button className="link-button" type="button" onClick={() => void handleRemoveMember(member.id)} disabled={working}>Remove</button> : null}</div>)}
                  {!members.length && <p className="muted">No members found.</p>}
                </div>
                {isOwner && <div className="forms-row">
                  <form onSubmit={handleAddMember}><h3>Add member</h3><label htmlFor="member-email">Email</label><input id="member-email" type="email" value={memberEmail} onChange={(event) => setMemberEmail(event.target.value)} required /><button className="button" type="submit" disabled={working}>Add member</button></form>
                  <form onSubmit={handleTransferOwnership}><h3>Transfer ownership</h3><label htmlFor="transfer-email">Member email</label><input id="transfer-email" type="email" value={transferEmail} onChange={(event) => setTransferEmail(event.target.value)} required /><button className="button secondary" type="submit" disabled={working}>Transfer</button></form>
                </div>}
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
