import { FormEvent, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  addOrganizationMember, addProjectMember, listOrganizationMembers, listProjectMembers,
  removeProjectMember, transferProjectOwnership,
  type AuthUser, type Organization, type Project,
} from "./api";

type Props = {
  user: AuthUser; organizations: Organization[]; projects: Project[];
  organizationId: string; projectId: string; loading: boolean; error: string;
  onOrganizationChange: (id: string) => void; onProjectChange: (id: string) => void;
  onClose: () => void; onProjectUpdated: (project: Project) => void;
};

export function MembersPage(props: Props) {
  const [section, setSection] = useState<"organization" | "project">("organization");
  const organization = props.organizations.find((item) => item.id === props.organizationId);
  const project = props.projects.find((item) => item.id === props.projectId && item.organization_id === props.organizationId);
  const resource = section === "organization" ? organization : project;
  return <main className="workspace-shell">
    <header className="workspace-header">
      <div><div className="eyebrow">FreeSelfTrack</div><h1>Members</h1></div>
      <div className="workspace-actions"><button className="button secondary compact" type="button" onClick={props.onClose}>Back to workspace</button></div>
    </header>
    <div className="members-context">
      <div><label htmlFor="members-organization">Organization</label>
        <select id="members-organization" value={props.organizationId} onChange={(event) => props.onOrganizationChange(event.target.value)}>
          <option value="">No organization selected</option>
          {props.organizations.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></div>
      <div><label htmlFor="members-project">Project</label>
        <select id="members-project" value={project?.id ?? ""} disabled={props.loading || !props.projects.length} onChange={(event) => props.onProjectChange(event.target.value)}>
          <option value="">No project selected</option>
          {props.projects.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
        </select></div>
    </div>
    {props.loading && <p role="status">Loading resources...</p>}
    {props.error && <p className="error" role="alert">{props.error}</p>}
    <nav className="mode-switch" aria-label="Member scope">
      <button className={section === "organization" ? "tab active" : "tab"} aria-pressed={section === "organization"} onClick={() => setSection("organization")}>Organization members</button>
      <button className={section === "project" ? "tab active" : "tab"} aria-pressed={section === "project"} onClick={() => setSection("project")}>Project members</button>
    </nav>
    {resource ? <MemberList key={section + resource.id} scope={section} resource={resource} user={props.user} onProjectUpdated={props.onProjectUpdated} /> : <p className="empty-state">{section === "organization" ? "No organization selected." : "No project selected."}</p>}
  </main>;
}

function MemberList({ scope, resource, user, onProjectUpdated }: {
  scope: "organization" | "project"; resource: Organization | Project; user: AuthUser;
  onProjectUpdated: (project: Project) => void;
}) {
  const client = useQueryClient();
  const queryKey = [scope + "-members", resource.id];
  const members = useQuery({ queryKey, queryFn: () => scope === "organization" ? listOrganizationMembers(resource.id) : listProjectMembers(resource.id) });
  const [email, setEmail] = useState("");
  const [transferEmail, setTransferEmail] = useState("");
  const [notice, setNotice] = useState("");
  const owner = resource.owner_id === user.id;
  const refresh = () => client.invalidateQueries({ queryKey });
  const add = useMutation({
    mutationFn: (value: string) => scope === "organization" ? addOrganizationMember(resource.id, value) : addProjectMember(resource.id, value),
    onSuccess: async () => { setEmail(""); setNotice("Membership confirmed."); await refresh(); },
  });
  const remove = useMutation({ mutationFn: (id: string) => removeProjectMember(resource.id, id), onSuccess: refresh });
  const transfer = useMutation({
    mutationFn: () => transferProjectOwnership(resource.id, transferEmail.trim()),
    onSuccess: (updated) => { onProjectUpdated(updated); setTransferEmail(""); setNotice("Ownership transferred."); },
  });
  const pending = add.isPending || remove.isPending || transfer.isPending;
  const error = add.error || remove.error || transfer.error;
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!owner || pending) return;
    setNotice(""); remove.reset(); transfer.reset();
    add.mutate(email.trim());
  }
  return <section className="members-content" aria-labelledby="member-list-title">
    <h2 id="member-list-title">{resource.name}</h2>
    {members.isPending && <p role="status">Loading members...</p>}
    {members.isError && <div><p className="error" role="alert">{members.error.message}</p><button className="button secondary compact" onClick={() => void members.refetch()} disabled={members.isFetching}>Retry</button></div>}
    {members.isSuccess && <>
      <ul className="members-directory">{members.data.map((member) => <li className="member-row" key={member.id}>
        <span>{member.profile ? member.profile.first_name + " " + member.profile.last_name : "Profile unavailable"}</span>
        {member.id === resource.owner_id ? <span className="role">Owner</span> : owner && scope === "project" ? <button className="link-button" disabled={pending} onClick={() => { setNotice(""); add.reset(); transfer.reset(); remove.mutate(member.id); }}>Remove</button> : null}
      </li>)}</ul>
      {!members.data.length && <p>No members found.</p>}
    </>}
    {owner && <form className="member-add-form" onSubmit={submit}>
      <h3>Add member</h3><label htmlFor="member-email">Email</label>
      <input id="member-email" type="email" required value={email} onChange={(event) => setEmail(event.target.value)} disabled={pending} />
      <button className="button compact" disabled={pending}>{add.isPending ? "Adding..." : "Add member"}</button>
    </form>}
    {error && <p className="error" role="alert">{error.message}</p>}
    {notice && <p className="notice" role="status">{notice}</p>}
    {owner && scope === "project" && <form className="member-add-form" onSubmit={(event) => { event.preventDefault(); if (pending) return; setNotice(""); add.reset(); remove.reset(); transfer.mutate(); }}>
      <h3>Transfer ownership</h3><label htmlFor="transfer-email">Member email</label>
      <input id="transfer-email" type="email" required value={transferEmail} onChange={(event) => setTransferEmail(event.target.value)} disabled={pending} />
      <button className="button secondary compact" disabled={pending}>{transfer.isPending ? "Transferring..." : "Transfer"}</button>
    </form>}
  </section>;
}
