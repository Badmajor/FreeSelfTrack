import { TaskChat } from "./TaskChat";
import { TaskLinks, type LinkSelection } from "./TaskLinks";
import {
  FormEvent,
  KeyboardEvent as ReactKeyboardEvent,
  PointerEvent as ReactPointerEvent,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Link2 } from "lucide-react";

import {
  addTaskWatcher,
  createTask,
  getBoard,
  getColumnTasks,
  getTask,
  getProject,
  listProjectMembers,
  getTaskHistory,
  listTaskWatchers,
  removeTaskWatcher,
  updateTask,
  type BoardColumn,
  type Priority,
  type Project,
  type Task,
  type TaskHistoryEntry,
  type UserSummary,
} from "./api";

type Props = {
  project: Project;
  currentUser: UserSummary;
  onClose?: () => void;
  onOpenTask?: (taskId: string) => void;
  onOpenLinkedTask?: (projectId: string, taskId: string) => void;
  canWrite?: boolean;
  linkSelection?: LinkSelection | null;
  onStartLinkSelection?: (selection: LinkSelection) => void;
  onCancelLinkSelection?: () => void;
  onSelectLinkedTask?: (taskId: string) => void;
};
type ColumnState = BoardColumn & { loadingMore: boolean; error: string };
const DEFAULT_WIDTH = 280;
const STORY_POINTS = [1, 2, 3, 5, 8, 13, 21] as const;
const PRIORITIES: Priority[] = ["low", "normal", "major", "critical"];

export function KanbanView({
  project,
  currentUser,
  onClose,
  onOpenTask,
  onOpenLinkedTask = (_, taskId) => onOpenTask?.(taskId),
  canWrite = true,
  linkSelection,
  onStartLinkSelection = () => undefined,
  onCancelLinkSelection = () => undefined,
  onSelectLinkedTask = () => undefined,
}: Props) {
  const queryClient = useQueryClient();
  const board = useQuery({
    queryKey: ["board", project.id],
    queryFn: () => getBoard(project.id),
  });
  const [columns, setColumns] = useState<ColumnState[]>([]);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const lastTriggerRef = useRef<HTMLElement | null>(null);
  const [draggedTask, setDraggedTask] = useState<Task | null>(null);
  const [widths, setWidths] = useState<Record<string, number>>(() =>
    readWidths(project.id),
  );
  const [error, setError] = useState("");

  useEffect(() => {
    if (board.data)
      setColumns(
        board.data.columns.map((column) => ({
          ...column,
          loadingMore: false,
          error: "",
        })),
      );
  }, [board.data]);
  useEffect(() => {
    window.localStorage.setItem(widthKey(project.id), JSON.stringify(widths));
  }, [project.id, widths]);

  const update = useMutation({
    mutationFn: ({ taskId, statusId }: { taskId: string; statusId: string }) =>
      updateTask(taskId, { status_id: statusId }),
    onSuccess: () =>
      void queryClient.invalidateQueries({ queryKey: ["board", project.id] }),
    onError: (requestError) => setError(messageFor(requestError)),
  });

  function changeStatus(task: Task, statusId: string) {
    if (task.status_id === statusId || update.isPending) return;
    update.mutate({ taskId: task.id, statusId });
  }

  async function loadMore(column: ColumnState) {
    if (!column.next_cursor || column.loadingMore) return;
    setColumns((current) =>
      current.map((item) =>
        item.status.id === column.status.id
          ? { ...item, loadingMore: true, error: "" }
          : item,
      ),
    );
    try {
      const page = await getColumnTasks(
        project.id,
        column.status.id,
        column.next_cursor,
      );
      setColumns((current) =>
        current.map((item) =>
          item.status.id === column.status.id
            ? {
                ...item,
                tasks: appendUnique(item.tasks, page.tasks),
                next_cursor: page.next_cursor,
                loadingMore: false,
              }
            : item,
        ),
      );
    } catch (requestError) {
      setColumns((current) =>
        current.map((item) =>
          item.status.id === column.status.id
            ? { ...item, loadingMore: false, error: messageFor(requestError) }
            : item,
        ),
      );
    }
  }

  const activeTask = useMemo(
    () =>
      columns
        .flatMap((column) => column.tasks)
        .find((task) => task.id === selectedTaskId) ?? null,
    [columns, selectedTaskId],
  );
  if (board.isPending)
    return (
      <section className="kanban-shell">
        <p className="loading">Loading Kanban...</p>
      </section>
    );
  if (board.isError)
    return (
      <section className="kanban-shell">
        <p className="error" role="alert">
          {messageFor(board.error)}
        </p>
        <button
          className="button secondary"
          type="button"
          onClick={() => void board.refetch()}
        >
          Retry
        </button>
      </section>
    );

  return (
    <section className="kanban-shell" aria-label={`${project.name} Kanban`}>
      <div className="kanban-heading">
        <div>
          <div className="eyebrow">Project board</div>
          <h2>{project.name}</h2>
        </div>
        <div className="kanban-actions">
          {onClose && (
            <button
              className="button secondary compact"
              type="button"
              onClick={onClose}
            >
              Back to project
            </button>
          )}
        </div>
      </div>
      {linkSelection && (
        <div className="link-selection-banner" role="status">
          <Link2 aria-hidden="true" />
          <span>
            Select a task for <strong>{linkSelection.sourceSlug}</strong> ·{" "}
            {linkSelection.relationType.replace("_", " ")}
          </span>
          <button type="button" className="button secondary compact" onClick={onCancelLinkSelection}>
            Cancel
          </button>
        </div>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      <div className="kanban-board">
        {columns.map((column) => (
          <KanbanColumn
            key={column.status.id}
            column={column}
            width={widths[column.status.id] ?? DEFAULT_WIDTH}
            onWidthChange={(width) =>
              setWidths((current) => ({
                ...current,
                [column.status.id]: width,
              }))
            }
            canWrite={canWrite}
            selecting={Boolean(linkSelection)}
            onCreate={async (title, storyPoints, dueDate, priority) => {
              await createTask(project.id, {
                title,
                description: null,
                status_id: column.status.id,
                story_points: storyPoints,
                due_date: dueDate,
                priority,
              });
              await queryClient.invalidateQueries({
                queryKey: ["board", project.id],
              });
            }}
            onTaskClick={(taskId, trigger) => {
              if (linkSelection) {
                if (taskId !== linkSelection.sourceTaskId) onSelectLinkedTask(taskId);
                return;
              }
              if (onOpenTask) {
                onOpenTask(taskId);
                return;
              }
              lastTriggerRef.current = trigger;
              setSelectedTaskId(taskId);
            }}
            onDragStart={setDraggedTask}
            onDrop={(statusId) => {
              if (draggedTask) changeStatus(draggedTask, statusId);
              setDraggedTask(null);
            }}
            onLoadMore={() => void loadMore(column)}
          />
        ))}
      </div>
      {activeTask && (
        <TaskDrawer
          key={activeTask.id}
          task={activeTask}
          columns={columns}
          projectId={project.id}
          organizationId={project.organization_id}
          canManageProject={project.capabilities?.edit ?? false}
          currentUser={currentUser}
          canWrite={canWrite}
          onOpenLinkedTask={onOpenLinkedTask}
          onStartLinkSelection={onStartLinkSelection}
          onClose={() => {
            setSelectedTaskId(null);
            requestAnimationFrame(() => lastTriggerRef.current?.focus());
          }}
          onSaved={(saved) =>
            setColumns((current) => replaceTask(current, saved))
          }
          onStatusChange={changeStatus}
        />
      )}
    </section>
  );
}

type ColumnProps = {
  column: ColumnState;
  width: number;
  onWidthChange: (width: number) => void;
  onCreate: (
    title: string,
    storyPoints: number | null,
    dueDate: string | null,
    priority: Priority | null,
  ) => Promise<void>;
  onTaskClick: (taskId: string, trigger: HTMLElement) => void;
  onDragStart: (task: Task) => void;
  onDrop: (statusId: string) => void;
  onLoadMore: () => void;
  canWrite: boolean;
  selecting: boolean;
};
function KanbanColumn({
  column,
  width,
  onWidthChange,
  onCreate,
  onTaskClick,
  onDragStart,
  onDrop,
  onLoadMore,
  canWrite,
  selecting,
}: ColumnProps) {
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [storyPoints, setStoryPoints] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [priority, setPriority] = useState<Priority | "">("");
  const [createError, setCreateError] = useState("");
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      await onCreate(
        title.trim(),
        storyPoints ? Number(storyPoints) : null,
        dueDate || null,
        priority || null,
      );
      setTitle("");
      setStoryPoints("");
      setDueDate("");
      setPriority("");
      setCreating(false);
    } catch (error) {
      setCreateError(messageFor(error));
    }
  }
  const resizeStart = (event: ReactPointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = width;
    const move = (moveEvent: globalThis.PointerEvent) =>
      onWidthChange(
        Math.min(520, Math.max(220, startWidth + moveEvent.clientX - startX)),
      );
    const stop = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", stop);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", stop);
  };
  const resizeKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    event.stopPropagation();
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      onWidthChange(
        Math.min(
          520,
          Math.max(220, width + (event.key === "ArrowRight" ? 20 : -20)),
        ),
      );
    }
  };
  return (
    <section
      className="kanban-column"
      style={{ width }}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        onDrop(column.status.id);
      }}
      aria-labelledby={`status-${column.status.id}`}
    >
      <header className="kanban-column-header">
        <div>
          <h3 id={`status-${column.status.id}`}>{column.status.name}</h3>
          <span>{column.tasks.length}</span>
          {column.status.is_completed ? (
            <span className="completion-badge">Completed</span>
          ) : null}
        </div>
        <div
          className="resize-handle"
          role="separator"
          aria-orientation="vertical"
          aria-label={`Resize ${column.status.name} column`}
          aria-valuemin={220}
          aria-valuemax={520}
          aria-valuenow={width}
          tabIndex={0}
          onPointerDown={resizeStart}
          onKeyDown={resizeKeyDown}
        />
      </header>
      <div
        className="task-list"
        onScroll={(event) => {
          const target = event.currentTarget;
          if (
            target.scrollTop + target.clientHeight >=
            target.scrollHeight - 24
          )
            onLoadMore();
        }}
      >
        {column.tasks.map((task) => (
          <TaskCard
            key={task.id}
            task={task}
            status={column.status}
            onClick={(trigger) => onTaskClick(task.id, trigger)}
            onDragStart={() => { if (canWrite && !selecting) onDragStart(task); }}
            selecting={selecting}
          />
        ))}
        {!column.tasks.length && (
          <p className="empty-state compact-empty">No tasks in this column.</p>
        )}
        {column.loadingMore && <p className="muted">Loading more...</p>}
        {column.error && (
          <p className="error" role="alert">
            {column.error}
          </p>
        )}
      </div>
      {canWrite && !selecting && <button
        className="button compact"
        type="button"
        onClick={() => setCreating((value) => !value)}
      >
        {creating ? "Cancel" : "Add task"}
      </button>}
      {canWrite && !selecting && creating && (
        <form
          className="create-task-form"
          onSubmit={(event) => void submit(event)}
        >
          <label htmlFor={`new-task-${column.status.id}`}>Title</label>
          <input
            id={`new-task-${column.status.id}`}
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            required
          />
          <div className="create-task-planning">
            <label htmlFor={`new-task-points-${column.status.id}`}>
              Story points
              <select
                id={`new-task-points-${column.status.id}`}
                value={storyPoints}
                onChange={(event) => setStoryPoints(event.target.value)}
              >
                <option value="">No estimate</option>
                {STORY_POINTS.map((points) => (
                  <option key={points} value={points}>
                    {points} SP
                  </option>
                ))}
              </select>
            </label>
            <label htmlFor={`new-task-due-${column.status.id}`}>
              Deadline
              <input
                id={`new-task-due-${column.status.id}`}
                type="date"
                value={dueDate}
                onChange={(event) => setDueDate(event.target.value)}
              />
            </label>
            <label htmlFor={`new-task-priority-${column.status.id}`}>
              Priority
              <select
                id={`new-task-priority-${column.status.id}`}
                value={priority}
                onChange={(event) =>
                  setPriority(event.target.value as Priority | "")
                }
              >
                <option value="">No priority</option>
                {PRIORITIES.map((item) => (
                  <option key={item} value={item}>
                    {priorityLabel(item)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <button className="button" type="submit">
            Create
          </button>
          {createError && (
            <p className="error" role="alert">
              {createError}
            </p>
          )}
        </form>
      )}
    </section>
  );
}

type CardProps = {
  task: Task;
  status: BoardColumn["status"];
  onClick: (trigger: HTMLElement) => void;
  onDragStart: () => void;
  selecting: boolean;
};
function TaskCard({ task, status, onClick, onDragStart, selecting }: CardProps) {
  const overdue = Boolean(
    task.due_date && !status.is_completed && utcDate() > task.due_date,
  );
  return (
    <article
      className={`task-card${overdue ? " overdue" : ""}${selecting ? " link-selectable" : ""}`}
      draggable={!selecting}
      onDragStart={onDragStart}
      onClick={(event) => onClick(event.currentTarget)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onClick(event.currentTarget);
        }
      }}
      tabIndex={0}
      aria-label={`${selecting ? "Select" : "Open"} task ${task.id}`}
    >
      <strong>{task.title}</strong>
      <span>{task.slug ?? task.id}</span>
      <div className="task-badges">
        {task.story_points !== null && (
          <span className="task-badge story-points">
            {task.story_points} SP
          </span>
        )}
        {task.priority && (
          <span className={`task-badge priority priority-${task.priority}`}>
            {priorityLabel(task.priority)}
          </span>
        )}
        {task.due_date && (
          <time className="task-badge" dateTime={task.due_date}>
            Due {formatDate(task.due_date)}
          </time>
        )}
      </div>
      <time dateTime={task.updated_at}>
        Updated {new Date(task.updated_at).toLocaleString()}
      </time>
      <span>
        {task.assignee
          ? `Assignee: ${task.assignee.first_name} ${task.assignee.last_name}`
          : "Unassigned"}
      </span>
      <span>Watchers: {task.watchers.length}</span>
      <span className="task-status" aria-label={`Status: ${status.name}`}>
        Status: {status.name}
      </span>
    </article>
  );
}

type DrawerProps = {
  task: Task;
  columns: ColumnState[];
  projectId: string;
  organizationId: string;
  canManageProject: boolean;
  currentUser: UserSummary;
  canWrite: boolean;
  focusCommentId?: string;
  initialActivity?: "chat" | "links" | "history";
  onOpenLinkedTask: (projectId: string, taskId: string) => void;
  onStartLinkSelection: (selection: LinkSelection) => void;
  onClose: () => void;
  onSaved: (task: Task) => void;
  onStatusChange: (task: Task, statusId: string) => void;
};
function TaskDrawer({
  task,
  columns,
  projectId,
  organizationId,
  canManageProject,
  currentUser,
  canWrite,
  focusCommentId,
  initialActivity = "chat",
  onOpenLinkedTask,
  onStartLinkSelection,
  onClose,
  onSaved,
  onStatusChange,
}: DrawerProps) {
  const queryClient = useQueryClient();
  const [activity, setActivity] = useState<"chat" | "links" | "history">(
    initialActivity,
  );
  const details = useQuery({
    queryKey: ["task", task.id],
    queryFn: () => getTask(task.id),
  });
  const history = useQuery({
    queryKey: ["task-history", task.id],
    queryFn: () => getTaskHistory(task.id),
    enabled: activity === "history",
  });
  const watchers = useQuery({
    queryKey: ["task-watchers", task.id],
    queryFn: () => listTaskWatchers(task.id),
    enabled: canWrite,
  });
  const members = useQuery({
    queryKey: ["project-members", projectId],
    queryFn: () => listProjectMembers(projectId),
    enabled: canWrite,
  });
  const [title, setTitle] = useState(task.title);
  const [description, setDescription] = useState(task.description ?? "");
  const [reporterId, setReporterId] = useState(task.reporter_id);
  const [assigneeId, setAssigneeId] = useState(task.assignee_id ?? "");
  const [storyPoints, setStoryPoints] = useState(
    task.story_points === null ? "" : String(task.story_points),
  );
  const [dueDate, setDueDate] = useState(task.due_date ?? "");
  const [priority, setPriority] = useState<Priority | "">(task.priority ?? "");
  const [expandedHistory, setExpandedHistory] = useState<
    Record<string, boolean>
  >({});
  const [saveError, setSaveError] = useState("");
  const currentTask = details.data ?? task;
  const canManagePlanning =
    canWrite &&
    (canManageProject ||
    currentUser.id === currentTask.reporter_id ||
    currentUser.id === currentTask.assignee_id);
  const save = useMutation({
    mutationFn: () =>
      updateTask(task.id, {
        title,
        description,
        ...(canManagePlanning
          ? {
              story_points: storyPoints ? Number(storyPoints) : null,
              due_date: dueDate || null,
              priority: priority || null,
            }
          : {}),
      }),
    onSuccess: (saved) => {
      onSaved(saved);
      queryClient.setQueryData(["task", task.id], saved);
      setStoryPoints(
        saved.story_points === null ? "" : String(saved.story_points),
      );
      setDueDate(saved.due_date ?? "");
      setPriority(saved.priority ?? "");
      void queryClient.invalidateQueries({
        queryKey: ["task-history", task.id],
      });
    },
    onError: (error) => setSaveError(messageFor(error)),
  });
  const participantUpdate = useMutation({
    mutationFn: (change: {
      reporter_id?: string;
      assignee_id?: string | null;
    }) => updateTask(task.id, change),
    onSuccess: (saved) => {
      onSaved(saved);
      queryClient.setQueryData(["task", task.id], saved);
      setReporterId(saved.reporter_id);
      setAssigneeId(saved.assignee_id ?? "");
    },
    onError: (error) => {
      setReporterId(task.reporter_id);
      setAssigneeId(task.assignee_id ?? "");
      setSaveError(messageFor(error));
    },
  });
  const isWatching =
    watchers.data?.some((watcher) => watcher.id === currentUser.id) ??
    task.watchers.some((watcher) => watcher.id === currentUser.id);
  const watcherMutation = useMutation({
    mutationFn: () =>
      isWatching
        ? removeTaskWatcher(task.id, currentUser.id)
        : addTaskWatcher(task.id),
    onSuccess: () => void watchers.refetch(),
    onError: (error) => setSaveError(messageFor(error)),
  });
  const canChangeReporter =
    canWrite &&
    (canManageProject || currentUser.id === task.reporter_id);
  const canChangeAssignee =
    canWrite &&
    (canManageProject ||
      currentUser.id === task.assignee_id ||
      !task.assignee_id);

  useEffect(() => {
    if (details.data) {
      setTitle(details.data.title);
      setDescription(details.data.description ?? "");
      setReporterId(details.data.reporter_id);
      setAssigneeId(details.data.assignee_id ?? "");
      setStoryPoints(
        details.data.story_points === null
          ? ""
          : String(details.data.story_points),
      );
      setDueDate(details.data.due_date ?? "");
      setPriority(details.data.priority ?? "");
    }
  }, [details.data]);
  useEffect(() => {
    document.getElementById("task-title")?.focus();
  }, []);
  useEffect(() => {
    setReporterId(task.reporter_id);
    setAssigneeId(task.assignee_id ?? "");
  }, [task.assignee_id, task.reporter_id]);

  return (
    <aside
      className="task-drawer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="task-drawer-title"
    >
      <div className="drawer-header">
        <h2 id="task-drawer-title">Task details</h2>
        <div className="drawer-actions">
          {canWrite && <button
            className="button drawer-save"
            type="submit"
            form="task-edit-form"
            disabled={save.isPending}
          >
            {save.isPending ? "Saving..." : "Save changes"}
          </button>}
          <button
            className="icon-button"
            type="button"
            aria-label="Close task details"
            onClick={onClose}
          >
            ×
          </button>
        </div>
      </div>
      {details.isPending && <p className="loading">Loading task...</p>}
      <form
        id="task-edit-form"
        onSubmit={(event) => {
          event.preventDefault();
          if (!save.isPending) {
            setSaveError("");
            save.mutate();
          }
        }}
      >
        <label htmlFor="task-title">Title</label>
        <input
          id="task-title"
          value={title}
          readOnly={!canWrite}
          onChange={(event) => setTitle(event.target.value)}
        />
        <label htmlFor="task-description">Description</label>
        <textarea
          id="task-description"
          value={description}
          readOnly={!canWrite}
          onChange={(event) => setDescription(event.target.value)}
        />
        <div className="task-field-grid">
          <div className="task-field-row">
            <label htmlFor="task-status">Status</label>
            <select
              id="task-status"
              value={task.status_id}
              disabled={!canWrite}
              onChange={(event) => onStatusChange(task, event.target.value)}
            >
              {columns.map((column) => (
                <option key={column.status.id} value={column.status.id}>
                  {column.status.name}
                </option>
              ))}
            </select>
          </div>
          <div className="task-field-row">
            <label htmlFor="task-story-points">Story points</label>
            {canManagePlanning ? (
              <select
                id="task-story-points"
                value={storyPoints}
                disabled={save.isPending}
                onChange={(event) => setStoryPoints(event.target.value)}
              >
                <option value="">No estimate</option>
                {STORY_POINTS.map((points) => (
                  <option key={points} value={points}>
                    {points} SP
                  </option>
                ))}
              </select>
            ) : (
              <p className="readonly-value" id="task-story-points">
                {currentTask.story_points === null
                  ? "No estimate"
                  : `${currentTask.story_points} SP`}
              </p>
            )}
          </div>
          <div className="task-field-row">
            <label htmlFor="task-due-date">Deadline</label>
            {canManagePlanning ? (
              <input
                id="task-due-date"
                type="date"
                value={dueDate}
                disabled={save.isPending}
                onChange={(event) => setDueDate(event.target.value)}
              />
            ) : (
              <p className="readonly-value" id="task-due-date">
                {currentTask.due_date
                  ? formatDate(currentTask.due_date)
                  : "No deadline"}
              </p>
            )}
          </div>
          <div className="task-field-row">
            <label htmlFor="task-priority">Priority</label>
            {canManagePlanning ? (
              <select
                id="task-priority"
                value={priority}
                disabled={save.isPending}
                onChange={(event) =>
                  setPriority(event.target.value as Priority | "")
                }
              >
                <option value="">No priority</option>
                {PRIORITIES.map((item) => (
                  <option key={item} value={item}>
                    {priorityLabel(item)}
                  </option>
                ))}
              </select>
            ) : (
              <p className="readonly-value" id="task-priority">
                {currentTask.priority
                  ? priorityLabel(currentTask.priority)
                  : "No priority"}
              </p>
            )}
          </div>
        </div>
        {saveError && (
          <p className="error" role="alert">
            {saveError}
          </p>
        )}
      </form>
      <div className="drawer-section drawer-participants">
        <h3>Participants</h3>
        <div className="participant-row">
          <label htmlFor="task-reporter">Reporter</label>
          <select
            id="task-reporter"
            value={reporterId}
            disabled={!canChangeReporter || participantUpdate.isPending}
            onChange={(event) => {
              setReporterId(event.target.value);
              participantUpdate.mutate({ reporter_id: event.target.value });
            }}
          >
            {members.data?.map((member) => (
              <option key={member.id} value={member.id}>
                {profileName(member.profile)}
              </option>
            ))}
          </select>
        </div>
        <div className="participant-row">
          <label htmlFor="task-assignee">Assignee</label>
          <select
            id="task-assignee"
            value={assigneeId}
            disabled={!canChangeAssignee || participantUpdate.isPending}
            onChange={(event) => {
              const value = event.target.value || null;
              setAssigneeId(event.target.value);
              participantUpdate.mutate({ assignee_id: value });
            }}
          >
            <option value="">Unassigned</option>
            {members.data?.map((member) => (
              <option key={member.id} value={member.id}>
                {profileName(member.profile)}
              </option>
            ))}
          </select>
        </div>
        <div className="participant-row watcher-row">
          <span className="task-field-label">Watchers</span>
          <div className="watcher-control">
            <div
              className="watcher-list"
              aria-label={`Watchers: ${watchers.data?.length ?? task.watchers.length}`}
            >
              {watchers.data?.map((watcher) => (
                <span className="watcher" key={watcher.id}>
                  {participantName(watcher)}
                </span>
              ))}
            </div>
            {watchers.isPending && <p className="muted">Loading watchers...</p>}
            {watchers.isError && (
              <p className="error" role="alert">
                Unable to load watchers.
              </p>
            )}
            {!watchers.isPending &&
              !watchers.isError &&
              !watchers.data?.length && <p className="muted">No watchers.</p>}
            {canWrite && <button
              className="icon-button drawer-watch"
              type="button"
              disabled={watcherMutation.isPending}
              aria-label={isWatching ? "Stop watching" : "Watch task"}
              title={isWatching ? "Stop watching" : "Watch task"}
              onClick={() => watcherMutation.mutate()}
            >
              {isWatching ? (
                <EyeOff aria-hidden="true" />
              ) : (
                <Eye aria-hidden="true" />
              )}
            </button>}
          </div>
        </div>
      </div>
      <div className="drawer-section activity-section">
        <div
          role="tablist"
          aria-label="Task activity"
          onKeyDown={(event) => {
            if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key))
              return;
            event.preventDefault();
            const tabs = ["chat", "links", "history"] as const;
            const current = tabs.indexOf(activity);
            const next =
              event.key === "Home"
                ? tabs[0]
                : event.key === "End"
                  ? tabs[2]
                  : tabs[(current + (event.key === "ArrowRight" ? 1 : 2)) % 3];
            setActivity(next);
            document.getElementById("activity-" + next)?.focus();
          }}
        >
          <button
            type="button"
            role="tab"
            id="activity-chat"
            aria-controls="activity-chat-panel"
            tabIndex={activity === "chat" ? 0 : -1}
            aria-selected={activity === "chat"}
            onClick={() => setActivity("chat")}
          >
            Chat
          </button>
          <button
            type="button"
            role="tab"
            id="activity-links"
            aria-controls="activity-links-panel"
            tabIndex={activity === "links" ? 0 : -1}
            aria-selected={activity === "links"}
            onClick={() => setActivity("links")}
          >
            Links
          </button>
          <button
            type="button"
            role="tab"
            id="activity-history"
            aria-controls="activity-history-panel"
            tabIndex={activity === "history" ? 0 : -1}
            aria-selected={activity === "history"}
            onClick={() => setActivity("history")}
          >
            History
          </button>
        </div>
        <div
          role="tabpanel"
          id="activity-chat-panel"
          aria-labelledby="activity-chat"
          hidden={activity !== "chat"}
        >
          <TaskChat
            key={task.id}
            taskId={task.id}
            organizationId={organizationId}
            focusCommentId={focusCommentId}
          />
        </div>
        <div
          role="tabpanel"
          id="activity-links-panel"
          aria-labelledby="activity-links"
          hidden={activity !== "links"}
        >
          <TaskLinks
            taskId={task.id}
            taskSlug={task.slug}
            projectId={projectId}
            organizationId={organizationId}
            canManage={canWrite}
            onOpenTask={onOpenLinkedTask}
            onStartSelection={onStartLinkSelection}
          />
        </div>
        <div
          role="tabpanel"
          id="activity-history-panel"
          aria-labelledby="activity-history"
          hidden={activity !== "history"}
        >
          <h3>History</h3>
          {history.isError && (
            <p className="error" role="alert">
              Unable to load history.{" "}
              <button type="button" onClick={() => void history.refetch()}>
                Retry history
              </button>
            </p>
          )}
          {history.isPending && <p className="muted">Loading history...</p>}
          {history.data?.entries.map((entry: TaskHistoryEntry) => {
            const expanded = expandedHistory[entry.id] ?? false;
            const text = formatHistoryEntry(entry);
            return (
              <div className="history-entry" key={entry.id}>
                <p>
                  <time dateTime={entry.created_at}>
                    {new Date(entry.created_at).toLocaleString()}
                  </time>{" "}
                  ·{" "}
                  <strong>
                    {entry.actor.first_name} {entry.actor.last_name}
                  </strong>{" "}
                  · {text}
                </p>
                {entry.field_name === "description" && entry.new_value && (
                  <details open={expanded}>
                    <summary
                      onClick={(event) => {
                        event.preventDefault();
                        setExpandedHistory((current) => ({
                          ...current,
                          [entry.id]: !expanded,
                        }));
                      }}
                    >
                      {expanded ? "Hide details" : "Show details"}
                    </summary>
                    <p>{entry.new_value}</p>
                  </details>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </aside>
  );
}

function formatHistoryEntry(entry: TaskHistoryEntry) {
  const labels: Record<string, string> = {
    status_changed: "changed status",
    title_changed: "changed title",
    description_changed: "changed description",
    reporter_changed: "changed reporter",
    assignee_changed: "changed assignee",
    watcher_added: "added a watcher",
    watcher_removed: "removed a watcher",
    story_points_changed: "changed story points",
    due_date_changed: "changed deadline",
    priority_changed: "changed priority",
  };
  const label = labels[entry.event_type] ?? entry.event_type;
  if (entry.event_type === "status_changed")
    return `${label}: ${entry.old_value ?? "none"} -> ${entry.new_value ?? "none"}`;
  if (entry.event_type === "watcher_added")
    return `${label} ${entry.new_value ?? ""}`;
  if (entry.event_type === "watcher_removed")
    return `${label} ${entry.old_value ?? ""}`;
  return `${label}${entry.field_name === "description" ? ": " + shorten(entry.new_value) : `: ${entry.old_value ?? "none"} -> ${entry.new_value ?? "none"}`}`;
}
function priorityLabel(priority: Priority) {
  return priority.charAt(0).toUpperCase() + priority.slice(1);
}
function profileName(
  profile: { first_name: string; last_name: string } | undefined,
) {
  return profile
    ? `${profile.first_name} ${profile.last_name}`
    : "Unknown user";
}
function participantName(participant: {
  first_name: string;
  last_name: string;
}) {
  return `${participant.first_name} ${participant.last_name}`;
}
function shorten(value: string | null | undefined) {
  if (!value) return "none";
  return value.length > 120 ? value.slice(0, 120) + "..." : value;
}
function utcDate() {
  return new Date().toISOString().slice(0, 10);
}
function formatDate(value: string) {
  return new Intl.DateTimeFormat(undefined, {
    timeZone: "UTC",
    year: "numeric",
    month: "short",
    day: "numeric",
  }).format(new Date(`${value}T00:00:00Z`));
}
function widthKey(projectId: string) {
  return `freeselftrack.kanban.widths.${projectId}`;
}
function readWidths(projectId: string): Record<string, number> {
  try {
    return JSON.parse(window.localStorage.getItem(widthKey(projectId)) ?? "{}");
  } catch {
    return {};
  }
}
function appendUnique(current: Task[], next: Task[]) {
  const ids = new Set(current.map((task) => task.id));
  return [...current, ...next.filter((task) => !ids.has(task.id))];
}
function replaceTask(columns: ColumnState[], task: Task): ColumnState[] {
  return columns.map((column) => ({
    ...column,
    tasks: column.tasks.map((item) => (item.id === task.id ? task : item)),
  }));
}
function messageFor(error: unknown) {
  return error instanceof Error ? error.message : "Request failed";
}

export function NotificationTaskPanel({
  taskId,
  commentId,
  initialActivity = "chat",
  currentUser,
  onOpenLinkedTask,
  onStartLinkSelection,
  onClose,
}: {
  taskId: string;
  commentId?: string;
  initialActivity?: "chat" | "links" | "history";
  currentUser: UserSummary;
  onOpenLinkedTask: (projectId: string, taskId: string) => void;
  onStartLinkSelection: (selection: LinkSelection) => void;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const task = useQuery({
    queryKey: ["task", taskId],
    queryFn: () => getTask(taskId),
    retry: false,
  });
  const project = useQuery({
    queryKey: ["project", task.data?.project_id],
    queryFn: () => getProject(task.data!.project_id),
    enabled: !!task.data,
    retry: false,
  });
  const board = useQuery({
    queryKey: ["board", task.data?.project_id],
    queryFn: () => getBoard(task.data!.project_id),
    enabled: !!task.data,
    retry: false,
  });
  const members = useQuery({
    queryKey: ["project-members", task.data?.project_id],
    queryFn: () => listProjectMembers(task.data!.project_id),
    enabled: !!task.data,
    retry: false,
  });
  const update = useMutation({
    mutationFn: (statusId: string) =>
      updateTask(taskId, { status_id: statusId }),
    onSuccess: (saved) => client.setQueryData(["task", taskId], saved),
  });
  if (task.isError || project.isError || board.isError)
    return (
      <aside className="task-drawer">
        <button type="button" onClick={onClose}>
          Close
        </button>
        <p role="alert">Task is unavailable.</p>
      </aside>
    );
  if (!task.data || !project.data || !board.data)
    return (
      <aside className="task-drawer">
        <button type="button" onClick={onClose}>
          Close
        </button>
        <p role="status">Loading task...</p>
      </aside>
    );
  return (
    <>
      <TaskDrawer
        key={taskId + (commentId ?? "")}
        task={task.data}
        columns={board.data.columns.map((column) => ({
          ...column,
          loadingMore: false,
          error: "",
        }))}
        projectId={project.data.id}
        organizationId={project.data.organization_id}
        canManageProject={project.data.capabilities?.edit ?? false}
        currentUser={currentUser}
        canWrite={members.isSuccess}
        focusCommentId={commentId}
        initialActivity={initialActivity}
        onOpenLinkedTask={onOpenLinkedTask}
        onStartLinkSelection={onStartLinkSelection}
        onClose={onClose}
        onSaved={(saved) => client.setQueryData(["task", taskId], saved)}
        onStatusChange={(_, statusId) => update.mutate(statusId)}
      />
      {update.isError && (
        <p className="notification-task-error" role="alert">
          {messageFor(update.error)}
        </p>
      )}
    </>
  );
}
