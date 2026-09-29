import { FormEvent, KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent, useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addTaskWatcher,
  createTask,
  getBoard,
  getColumnTasks,
  getTask,
  listProjectMembers,
  getTaskHistory,
  listTaskWatchers,
  removeTaskWatcher,
  updateTask,
  type BoardColumn,
  type Project,
  type Task,
  type TaskHistoryEntry,
  type UserSummary,
} from "./api";

type Props = { project: Project; currentUser: UserSummary; onClose: () => void };
type ColumnState = BoardColumn & { loadingMore: boolean; error: string };
const DEFAULT_WIDTH = 280;

export function KanbanView({ project, currentUser, onClose }: Props) {
  const queryClient = useQueryClient();
  const board = useQuery({ queryKey: ["board", project.id], queryFn: () => getBoard(project.id) });
  const [columns, setColumns] = useState<ColumnState[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const lastTriggerRef = useRef<HTMLElement | null>(null);
  const [draggedTask, setDraggedTask] = useState<Task | null>(null);
  const [widths, setWidths] = useState<Record<string, number>>(() => readWidths(project.id));
  const [error, setError] = useState("");

  useEffect(() => { if (board.data) setColumns(board.data.columns.map((column) => ({ ...column, loadingMore: false, error: "" }))); }, [board.data]);
  useEffect(() => { window.localStorage.setItem(widthKey(project.id), JSON.stringify(widths)); }, [project.id, widths]);

  const update = useMutation({
    mutationFn: ({ taskId, statusId }: { taskId: string; statusId: string }) => updateTask(taskId, { status_id: statusId }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: ["board", project.id] }),
    onError: (requestError) => setError(messageFor(requestError)),
  });

  function changeStatus(task: Task, statusId: string) {
    if (task.status_id === statusId || update.isPending) return;
    update.mutate({ taskId: task.id, statusId });
  }

  async function loadMore(column: ColumnState) {
    if (!column.next_cursor || column.loadingMore) return;
    setColumns((current) => current.map((item) => item.status.id === column.status.id ? { ...item, loadingMore: true, error: "" } : item));
    try {
      const page = await getColumnTasks(project.id, column.status.id, column.next_cursor);
      setColumns((current) => current.map((item) => item.status.id === column.status.id ? { ...item, tasks: appendUnique(item.tasks, page.tasks), next_cursor: page.next_cursor, loadingMore: false } : item));
    } catch (requestError) {
      setColumns((current) => current.map((item) => item.status.id === column.status.id ? { ...item, loadingMore: false, error: messageFor(requestError) } : item));
    }
  }

  const activeTask = useMemo(() => columns.flatMap((column) => column.tasks).find((task) => task.id === selectedTaskId) ?? null, [columns, selectedTaskId]);
  if (board.isPending) return <section className="kanban-shell"><p className="loading">Loading Kanban...</p></section>;
  if (board.isError) return <section className="kanban-shell"><p className="error" role="alert">{messageFor(board.error)}</p><button className="button secondary" type="button" onClick={() => void board.refetch()}>Retry</button></section>;

  return <section className="kanban-shell" aria-label={`${project.name} Kanban`}>
    <div className="kanban-heading"><div><div className="eyebrow">Project board</div><h2>{project.name}</h2></div><button className="button secondary compact" type="button" onClick={onClose}>Back to project</button></div>
    {error && <p className="error" role="alert">{error}</p>}
    <div className="kanban-board">{columns.map((column) => <KanbanColumn key={column.status.id} column={column} width={widths[column.status.id] ?? DEFAULT_WIDTH} onWidthChange={(width) => setWidths((current) => ({ ...current, [column.status.id]: width }))} onCreate={async (title) => { await createTask(project.id, { title, description: null, status_id: column.status.id }); await queryClient.invalidateQueries({ queryKey: ["board", project.id] }); }} onTaskClick={(taskId, trigger) => { lastTriggerRef.current = trigger; setSelectedTaskId(taskId); }} onDragStart={setDraggedTask} onDrop={(statusId) => { if (draggedTask) changeStatus(draggedTask, statusId); setDraggedTask(null); }} onLoadMore={() => void loadMore(column)} />)}</div>
    {activeTask && <TaskDrawer key={activeTask.id} task={activeTask} columns={columns} projectId={project.id} projectOwnerId={project.owner_id} currentUser={currentUser} onClose={() => { setSelectedTaskId(null); requestAnimationFrame(() => lastTriggerRef.current?.focus()); }} onSaved={(saved) => setColumns((current) => replaceTask(current, saved))} onStatusChange={changeStatus} />}
  </section>;
}

type ColumnProps = { column: ColumnState; width: number; onWidthChange: (width: number) => void; onCreate: (title: string) => Promise<void>; onTaskClick: (taskId: string, trigger: HTMLElement) => void; onDragStart: (task: Task) => void; onDrop: (statusId: string) => void; onLoadMore: () => void };
function KanbanColumn({ column, width, onWidthChange, onCreate, onTaskClick, onDragStart, onDrop, onLoadMore }: ColumnProps) {
  const [creating, setCreating] = useState(false); const [title, setTitle] = useState(""); const [createError, setCreateError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) { event.preventDefault(); if (!title.trim()) return; try { await onCreate(title.trim()); setTitle(""); setCreating(false); } catch (error) { setCreateError(messageFor(error)); } }
  const resizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const move = (moveEvent: globalThis.PointerEvent) => onWidthChange(Math.min(520, Math.max(220, startWidth + moveEvent.clientX - startX)));
    const stop = () => { window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", stop); };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  const resizeKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      onWidthChange(Math.min(520, Math.max(220, width + (event.key === "ArrowRight" ? 20 : -20))));
    }
  };
  return <section className="kanban-column" style={{ width }} onDragOver={(event) => event.preventDefault()} onDrop={() => onDrop(column.status.id)} aria-labelledby={`status-${column.status.id}`}>
    <header className="kanban-column-header"><div><h3 id={`status-${column.status.id}`}>{column.status.name}</h3><span>{column.tasks.length}</span></div><div className="resize-handle" role="separator" aria-orientation="vertical" aria-label={`Resize ${column.status.name} column`} aria-valuemin={220} aria-valuemax={520} aria-valuenow={width} tabIndex={0} onPointerDown={resizeStart} onKeyDown={resizeKeyDown} /></header>
    <div className="task-list" onScroll={(event) => { const target = event.currentTarget; if (target.scrollTop + target.clientHeight >= target.scrollHeight - 24) onLoadMore(); }}>{column.tasks.map((task) => <TaskCard key={task.id} task={task} statusName={column.status.name} onClick={(trigger) => onTaskClick(task.id, trigger)} onDragStart={() => onDragStart(task)} />)}{!column.tasks.length && <p className="empty-state compact-empty">No tasks in this column.</p>}{column.loadingMore && <p className="muted">Loading more...</p>}{column.error && <p className="error" role="alert">{column.error}</p>}</div>
    <button className="button compact" type="button" onClick={() => setCreating((value) => !value)}>{creating ? "Cancel" : "Add task"}</button>{creating && <form className="create-task-form" onSubmit={(event) => void submit(event)}><label htmlFor={`new-task-${column.status.id}`}>Title</label><input id={`new-task-${column.status.id}`} value={title} onChange={(event) => setTitle(event.target.value)} required /><button className="button" type="submit">Create</button>{createError && <p className="error" role="alert">{createError}</p>}</form>}
  </section>;
}

type CardProps = { task: Task; statusName: string; onClick: (trigger: HTMLElement) => void; onDragStart: () => void };
function TaskCard({ task, statusName, onClick, onDragStart }: CardProps) { return <article className="task-card" draggable onDragStart={onDragStart} onClick={(event) => onClick(event.currentTarget)} onKeyDown={(event) => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onClick(event.currentTarget); } }} tabIndex={0} aria-label={`Open task ${task.id}`}><strong>{task.title}</strong><span>{task.slug ?? task.id}</span><time dateTime={task.updated_at}>Updated {new Date(task.updated_at).toLocaleString()}</time><span>{task.assignee ? `Assignee: ${task.assignee.first_name} ${task.assignee.last_name}` : "Unassigned"}</span><span>Watchers: {task.watchers.length}</span><span className="task-status" aria-label={`Status: ${statusName}`}>Status: {statusName}</span></article>; }

type DrawerProps = { task: Task; columns: ColumnState[]; projectId: string; projectOwnerId: string; currentUser: UserSummary; onClose: () => void; onSaved: (task: Task) => void; onStatusChange: (task: Task, statusId: string) => void };
function TaskDrawer({ task, columns, projectId, projectOwnerId, currentUser, onClose, onSaved, onStatusChange }: DrawerProps) {
  const details = useQuery({ queryKey: ["task", task.id], queryFn: () => getTask(task.id) });
  const history = useQuery({ queryKey: ["task-history", task.id], queryFn: () => getTaskHistory(task.id) });
  const watchers = useQuery({ queryKey: ["task-watchers", task.id], queryFn: () => listTaskWatchers(task.id) });
  const members = useQuery({ queryKey: ["project-members", projectId], queryFn: () => listProjectMembers(projectId) });
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? "");
  const [reporterId, setReporterId] = useState(task.reporter_id);
  const [assigneeId, setAssigneeId] = useState(task.assignee_id ?? "");
  const [expandedHistory, setExpandedHistory] = useState<Record<string, boolean>>({});
  const [saveError, setSaveError] = useState("");
  const save = useMutation({ mutationFn: () => updateTask(task.id, { title, description }), onSuccess: onSaved, onError: (error) => setSaveError(messageFor(error)) });
  const participantUpdate = useMutation({
    mutationFn: (change: { reporter_id?: string; assignee_id?: string | null }) => updateTask(task.id, change),
    onSuccess: (saved) => { onSaved(saved); setReporterId(saved.reporter_id); setAssigneeId(saved.assignee_id ?? ""); },
    onError: (error) => { setReporterId(task.reporter_id); setAssigneeId(task.assignee_id ?? ""); setSaveError(messageFor(error)); },
  });
  const isWatching = watchers.data?.some((watcher) => watcher.id === currentUser.id) ?? task.watchers.some((watcher) => watcher.id === currentUser.id);
  const watcherMutation = useMutation({
    mutationFn: () => isWatching ? removeTaskWatcher(task.id, currentUser.id) : addTaskWatcher(task.id),
    onSuccess: () => void watchers.refetch(),
    onError: (error) => setSaveError(messageFor(error)),
  });
  const canChangeReporter = currentUser.id === projectOwnerId || currentUser.id === task.reporter_id;
  const canChangeAssignee = currentUser.id === projectOwnerId || currentUser.id === task.assignee_id || !task.assignee_id;

  useEffect(() => {
    if (details.data) { setTitle(details.data.title); setDescription(details.data.description ?? ""); setReporterId(details.data.reporter_id); setAssigneeId(details.data.assignee_id ?? ""); }
  }, [details.data]);
  useEffect(() => { document.getElementById("task-title")?.focus(); }, []);
  useEffect(() => { setReporterId(task.reporter_id); setAssigneeId(task.assignee_id ?? ""); }, [task.assignee_id, task.reporter_id]);

  return <aside className="task-drawer" role="dialog" aria-modal="true" aria-labelledby="task-drawer-title">
    <div className="drawer-header"><h2 id="task-drawer-title">Task details</h2><button className="icon-button" type="button" aria-label="Close task details" onClick={onClose}>×</button></div>
    {details.isPending && <p className="loading">Loading task...</p>}
    <form onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
      <label htmlFor="task-title">Title</label><input id="task-title" value={title} onChange={(event) => setTitle(event.target.value)} />
      <label htmlFor="task-description">Description</label><textarea id="task-description" value={description} onChange={(event) => setDescription(event.target.value)} />
      <label htmlFor="task-status">Status</label><select id="task-status" value={task.status_id} onChange={(event) => onStatusChange(task, event.target.value)}>{columns.map((column) => <option key={column.status.id} value={column.status.id}>{column.status.name}</option>)}</select>
      <button className="button" type="submit" disabled={save.isPending}>Save changes</button>
      {saveError && <p className="error" role="alert">{saveError}</p>}
    </form>
    <div className="drawer-section"><h3>Participants</h3>
      <label htmlFor="task-reporter">Reporter</label><select id="task-reporter" value={reporterId} disabled={!canChangeReporter || participantUpdate.isPending} onChange={(event) => { setReporterId(event.target.value); participantUpdate.mutate({ reporter_id: event.target.value }); }}>{members.data?.map((member) => <option key={member.id} value={member.id}>{member.email}</option>)}</select>
      <label htmlFor="task-assignee">Assignee</label><select id="task-assignee" value={assigneeId} disabled={!canChangeAssignee || participantUpdate.isPending} onChange={(event) => { const value = event.target.value || null; setAssigneeId(event.target.value); participantUpdate.mutate({ assignee_id: value }); }}><option value="">Unassigned</option>{members.data?.map((member) => <option key={member.id} value={member.id}>{member.email}</option>)}</select>
      <p>Watchers: {watchers.data?.length ?? task.watchers.length}</p>{watchers.isPending && <p className="muted">Loading watchers...</p>}{watchers.isError && <p className="error" role="alert">Unable to load watchers.</p>}{!watchers.isPending && !watchers.isError && !watchers.data?.length && <p className="muted">No watchers.</p>}<div className="watcher-list">{watchers.data?.map((watcher) => <span className="watcher" key={watcher.id}>{watcher.email}</span>)}</div>
      <button className="button secondary compact" type="button" disabled={watcherMutation.isPending} onClick={() => watcherMutation.mutate()}>{isWatching ? "Stop watching" : "Watch task"}</button>
    </div>
    <div className="drawer-section"><h3>History</h3>{history.isPending && <p className="muted">Loading history...</p>}{history.data?.entries.map((entry: TaskHistoryEntry) => { const expanded = expandedHistory[entry.id] ?? false; const text = formatHistoryEntry(entry); return <div className="history-entry" key={entry.id}><p><time dateTime={entry.created_at}>{new Date(entry.created_at).toLocaleString()}</time> · <strong>{entry.actor.first_name} {entry.actor.last_name}</strong> · {text}</p>{entry.field_name === "description" && entry.new_value && <details open={expanded}><summary onClick={(event) => { event.preventDefault(); setExpandedHistory((current) => ({ ...current, [entry.id]: !expanded })); }}>{expanded ? "Hide details" : "Show details"}</summary><p>{entry.new_value}</p></details>}</div>; })}</div>
  </aside>;
}

function formatHistoryEntry(entry: TaskHistoryEntry) { const labels: Record<string, string> = { status_changed: "changed status", title_changed: "changed title", description_changed: "changed description", reporter_changed: "changed reporter", assignee_changed: "changed assignee", watcher_added: "added a watcher", watcher_removed: "removed a watcher" }; const label = labels[entry.event_type] ?? entry.event_type; if (entry.event_type === "status_changed") return `${label}: ${entry.old_value ?? "none"} -> ${entry.new_value ?? "none"}`; if (entry.event_type === "watcher_added") return `${label} ${entry.new_value ?? ""}`; if (entry.event_type === "watcher_removed") return `${label} ${entry.old_value ?? ""}`; return `${label}${entry.field_name === "description" ? ": " + shorten(entry.new_value) : `: ${entry.old_value ?? "none"} -> ${entry.new_value ?? "none"}`}`; }
function shorten(value: string | null | undefined) { if (!value) return "none"; return value.length > 120 ? value.slice(0, 120) + "..." : value; }
function widthKey(projectId: string) { return `freeselftrack.kanban.widths.${projectId}`; }
function readWidths(projectId: string): Record<string, number> { try { return JSON.parse(window.localStorage.getItem(widthKey(projectId)) ?? "{}"); } catch { return {}; } }
function appendUnique(current: Task[], next: Task[]) { const ids = new Set(current.map((task) => task.id)); return [...current, ...next.filter((task) => !ids.has(task.id))]; }
function replaceTask(columns: ColumnState[], task: Task): ColumnState[] { return columns.map((column) => ({ ...column, tasks: column.tasks.map((item) => item.id === task.id ? task : item) })); }
function messageFor(error: unknown) { return error instanceof Error ? error.message : "Request failed"; }
