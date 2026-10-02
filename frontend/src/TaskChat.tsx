import { FormEvent, KeyboardEvent, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useQuery } from "@tanstack/react-query";
import { Paperclip, Send, X } from "lucide-react";
import { ApiError, getAttachment, getComment, getComments, listOrganizationMembers, sendComment, type ChatAttachment, type ChatMessage } from "./api";

function forbidden(error: unknown) { return error instanceof ApiError && [401, 403, 404].includes(error.status); }
function message(error: unknown) { return error instanceof Error ? error.message : "Request failed"; }
function merge(previous: ChatMessage[], next: ChatMessage[]) { const items = new Map(previous.map((item) => [item.id, item])); next.forEach((item) => items.set(item.id, item)); return [...items.values()].sort((a, b) => a.sequence - b.sequence); }

export function TaskChat({ taskId, organizationId, focusCommentId }: { taskId: string; organizationId: string; focusCommentId?: string }) {
  const [focusedMessage, setFocusedMessage] = useState<ChatMessage | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [more, setMore] = useState(false);
  const [error, setError] = useState("");
  const [denied, setDenied] = useState(false);
  const [checkingFile, setCheckingFile] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [newMessages, setNewMessages] = useState(false);
  const [text, setText] = useState("");
  const [mentionIds, setMentionIds] = useState<string[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState("");
  const [uploadKey, setUploadKey] = useState(0);
  const requestId = useRef(crypto.randomUUID());
  const generation = useRef(0);
  const scroll = useRef<HTMLDivElement>(null);
  const bottom = useRef(true);
  const members = useQuery({ queryKey: ["organization-members", organizationId], queryFn: () => listOrganizationMembers(organizationId), enabled: !denied });
  const mentionSearch = text.match(/@([^@\n]*)$/)?.[1];
  const candidates = mentionSearch === undefined ? [] : (members.data ?? []).filter((member) => member.profile && !mentionIds.includes(member.id) && (member.profile.first_name + " " + member.profile.last_name).toLowerCase().includes(mentionSearch.toLowerCase()));
  function toBottom() { const node = scroll.current; if (node) node.scrollTop = node.scrollHeight; bottom.current = true; setNewMessages(false); }
  function rejectAccess() { setDenied(true); setMessages([]); setFocusedMessage(null); }

  useEffect(() => {
    const token = ++generation.current;
    let alive = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let newest = 0;
    setLoading(true); setLoadingOlder(false); setCheckingFile(null); setError(""); setDenied(false); setMessages([]);
    const current = () => alive && generation.current === token;
    async function poll() {
      try {
        const page = await getComments(taskId, { after: newest });
        if (!current()) return;
        if (page.comments.length) {
          newest = page.comments[page.comments.length - 1].sequence;
          setMessages((items) => merge(items, page.comments));
          if (bottom.current) requestAnimationFrame(toBottom); else setNewMessages(true);
        }
        setError("");
        timer = setTimeout(() => void poll(), page.has_more ? 0 : 3000);
      } catch (err) {
        if (!current()) return;
        if (forbidden(err)) { rejectAccess(); setError("Task access is no longer available."); return; }
        setError(message(err)); timer = setTimeout(() => void poll(), 3000);
      }
    }
    async function start() {
      try {
        const [page, target] = await Promise.all([
          getComments(taskId),
          focusCommentId ? getComment(taskId, focusCommentId) : Promise.resolve(null),
        ]);
        if (!current()) return;
        setMessages(page.comments); setFocusedMessage(target); setMore(page.has_more);
        newest = page.comments.at(-1)?.sequence ?? 0;
        setLoading(false);
        requestAnimationFrame(() => { if (!current()) return; if (focusCommentId) { bottom.current = false; document.getElementById("comment-" + focusCommentId)?.scrollIntoView({ block: "nearest" }); } else toBottom(); });
        timer = setTimeout(() => void poll(), 0);
      } catch (err) { if (current()) { setError(message(err)); setLoading(false); if (forbidden(err)) rejectAccess(); } }
    }
    void start();
    return () => { alive = false; generation.current = token + 1; clearTimeout(timer); };
  }, [taskId, focusCommentId, revision]);

  async function older() {
    if (!more || loadingOlder || !messages.length) return;
    const token = generation.current;
    const node = scroll.current;
    const height = node?.scrollHeight ?? 0;
    const top = node?.scrollTop ?? 0;
    setLoadingOlder(true);
    try {
      const page = await getComments(taskId, { before: messages[0].sequence });
      if (token !== generation.current) return;
      setMessages((items) => merge(items, page.comments)); setMore(page.has_more); setError("");
      requestAnimationFrame(() => { if (node && token === generation.current) node.scrollTop = top + node.scrollHeight - height; });
    } catch (err) { if (token === generation.current) { setError(message(err)); if (forbidden(err)) rejectAccess(); } }
    finally { if (token === generation.current) setLoadingOlder(false); }
  }
  function changed() { requestId.current = crypto.randomUUID(); setSendError(""); }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (sending || denied || (!text.trim() && !files.length)) return;
    setSending(true); setSendError(""); const token = generation.current;
    try {
      await sendComment(taskId, text, mentionIds, files, requestId.current);
      if (token !== generation.current) return;
      setText(""); setFiles([]); setMentionIds([]); setUploadKey((key) => key + 1); changed();
      // Poll from the last received sequence so concurrent messages are not skipped.
      bottom.current = true;
    } catch (err) { if (token === generation.current) { setSendError(message(err)); if (forbidden(err)) rejectAccess(); } }
    finally { if (token === generation.current) setSending(false); }
  }
  function messageKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key !== "Enter" || event.shiftKey || event.nativeEvent.isComposing) return;
    event.preventDefault();
    event.currentTarget.form?.requestSubmit();
  }
  async function checkFiles(commentId: string) {
    const token = generation.current;
    setCheckingFile(commentId);
    try {
      const updated = await getComment(taskId, commentId);
      if (token !== generation.current) return;
      setMessages((items) => items.map((item) => item.id === updated.id ? updated : item));
      setFocusedMessage((item) => item?.id === updated.id ? updated : item);
    } catch (err) {
      if (token === generation.current) { setError(message(err)); if (forbidden(err)) rejectAccess(); }
    } finally { if (token === generation.current) setCheckingFile(null); }
  }
  function renderMessage(item: ChatMessage) { return <article id={"comment-" + item.id} key={item.id} className={item.id === focusCommentId ? "chat-message highlighted" : "chat-message"}>
          <header><strong>{item.author.first_name} {item.author.last_name}</strong><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString()}</time></header>
          <p className="chat-text">{item.text}</p>
          {item.mentions.length > 0 && <p className="chat-mentions">{item.mentions.map((person) => "@" + person.first_name + " " + person.last_name).join(", ")}</p>}
          {item.attachments.map((attachment) => <FileView key={attachment.id} file={attachment} />)}
          {item.attachments.some((attachment) => attachment.state === "pending") && <button className="link-button" type="button" disabled={checkingFile !== null} onClick={() => void checkFiles(item.id)}>Check file status</button>}
        </article>; }
  return <section aria-label="Task chat" className="task-chat">
    {loading && <p role="status">Loading messages...</p>}
    {error && <div><p className="error" role="alert">{error}</p>{!denied && <button type="button" className="link-button" disabled={sending} onClick={() => setRevision((value) => value + 1)}>Retry chat</button>}</div>}
    {!denied && <>
      <div ref={scroll} className="chat-messages" onScroll={() => { const node = scroll.current; if (!node) return; bottom.current = node.scrollHeight - node.scrollTop - node.clientHeight < 30; if (bottom.current) setNewMessages(false); if (node.scrollTop < 25) void older(); }}>
        {more && <button type="button" className="link-button" disabled={loadingOlder} onClick={() => void older()}>{loadingOlder ? "Loading..." : "Earlier messages"}</button>}
        {!loading && !messages.length && !error && <p>No messages yet.</p>}
        {focusedMessage && !messages.some((item) => item.id === focusedMessage.id) && <div className="notification-message"><h4>Selected message</h4>{renderMessage(focusedMessage)}<h4>Recent messages</h4></div>}
        {messages.map(renderMessage)}
      </div>
      {newMessages && <button type="button" className="button compact chat-action" onClick={toBottom}>New messages</button>}
      <form className="chat-composer" onSubmit={(event) => void submit(event)}>
        {files.length > 0 && <div className="chat-selected-files" aria-label="Selected attachments">{files.map((file) => <span key={file.name + file.lastModified}>{file.name}</span>)}</div>}
        <div className="chat-compose-row">
          <label className="chat-icon-button" htmlFor="chat-files" title="Attach files"><Paperclip aria-hidden="true" /><span className="visually-hidden">Attach files</span></label>
          <textarea id="chat-text" aria-label="Message" placeholder="Write a message" rows={1} value={text} maxLength={10000} disabled={sending} onKeyDown={messageKeyDown} onChange={(event) => { setText(event.target.value); changed(); }} />
          <button className="chat-icon-button chat-send" type="submit" title="Send message" aria-label={sending ? "Sending message" : "Send message"} disabled={sending || (!text.trim() && !files.length)}>{sending ? <span className="chat-sending" aria-hidden="true" /> : <Send aria-hidden="true" />}</button>
        </div>
        {candidates.length > 0 && <ul className="mention-options" aria-label="Mention an organization member">{candidates.map((member) => <li key={member.id}><button type="button" disabled={sending} onClick={() => { setMentionIds((ids) => [...ids, member.id]); setText(text.replace(/@([^@\n]*)$/, "")); changed(); document.getElementById("chat-text")?.focus(); }}>@{member.profile?.first_name} {member.profile?.last_name}</button></li>)}</ul>}
        {members.isError && <p className="error">Unable to load mention candidates.</p>}
        <div className="chat-mentions">{mentionIds.map((id) => { const person = members.data?.find((member) => member.id === id)?.profile; return <button type="button" disabled={sending} key={id} onClick={() => { setMentionIds(mentionIds.filter((item) => item !== id)); changed(); }} aria-label={"Remove mention " + (person?.first_name ?? "member")}>@{person?.first_name} {person?.last_name} ×</button>; })}</div>
        <input key={uploadKey} id="chat-files" className="visually-hidden" aria-label="Attachments" type="file" multiple disabled={sending} onChange={(event) => { const selected = Array.from(event.target.files ?? []); if (selected.length > 5 || selected.some((file) => file.size > 25 * 1024 * 1024)) { setSendError("Up to 5 files, 25 MB each."); setFiles([]); requestId.current = crypto.randomUUID(); event.target.value = ""; return; } setFiles(selected); changed(); }} />
        {sendError && <p className="error" role="alert">{sendError}</p>}
      </form>
    </>}
  </section>;
}

function FileView({ file }: { file: ChatAttachment }) {
  const [url, setUrl] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false); const [open, setOpen] = useState(false); const imageButton = useRef<HTMLButtonElement>(null);
  const available = file.state === "ready";
  const image = available && ["image/png", "image/jpeg", "image/gif", "image/webp"].includes(file.media_type);
  useEffect(() => {
    let alive = true; let objectUrl = "";
    if (image) void getAttachment(file.id, true).then((blob) => { if (alive) { objectUrl = URL.createObjectURL(blob); setUrl(objectUrl); } }).catch((err) => { if (alive) setError(message(err)); });
    return () => { alive = false; if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [file.id, image]);
  async function download() { setBusy(true); setError(""); try { const blob = await getAttachment(file.id); const objectUrl = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = objectUrl; link.download = file.filename; link.click(); setTimeout(() => URL.revokeObjectURL(objectUrl), 1000); } catch (err) { setError(message(err)); } finally { setBusy(false); } }
  function closePreview() { setOpen(false); imageButton.current?.focus(); }
  return <div className="chat-file">{image && url && <button ref={imageButton} className="chat-image-button" type="button" onClick={() => setOpen(true)} aria-label={`Open image ${file.filename}`}><img src={url} alt={file.filename} loading="lazy" /></button>}<button className="link-button" type="button" disabled={busy || !available} onClick={() => void download()}>{file.filename} ({Math.ceil(file.size / 1024)} KB)</button>{!available && <span role="status">{file.state === "pending" ? "Awaiting file review" : "File unavailable"}</span>}{error && <p className="error" role="alert">{error}</p>}{open && url && <ImageModal url={url} filename={file.filename} onClose={closePreview} />}</div>;
}

function ImageModal({ url, filename, onClose }: { url: string; filename: string; onClose: () => void }) {
  const closeButton = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();
    function closeOnEscape(event: globalThis.KeyboardEvent) { if (event.key === "Escape") { event.stopPropagation(); onClose(); } }
    document.addEventListener("keydown", closeOnEscape, true);
    return () => { document.removeEventListener("keydown", closeOnEscape, true); document.body.style.overflow = previousOverflow; };
  }, [onClose]);
  return createPortal(<div className="chat-image-modal" role="dialog" aria-modal="true" aria-label={`Image preview: ${filename}`} onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}><button ref={closeButton} className="chat-modal-close" type="button" onClick={onClose} aria-label="Close image preview" title="Close"><X aria-hidden="true" /></button><img src={url} alt={filename} /></div>, document.body);
}
