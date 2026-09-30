import { act, cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import * as api from "../api";
import { TaskChat } from "../TaskChat";
import { renderWithQueryClient } from "./test-utils";

const person = { user_id: "member", first_name: "Anna", last_name: "Smith" };
const row = (sequence = 1): api.ChatMessage => ({ id: "message-" + sequence, task_id: "task", sequence, author: person, text: "Message " + sequence, mentions: [], attachments: [], created_at: "2026-09-30T10:00:00Z" });
function mount(focusCommentId?: string) {
  vi.spyOn(api, "listProjectMembers").mockResolvedValue([{ id: "member", email: "member@example.com", is_active: true, profile: person }]);
  return renderWithQueryClient(<TaskChat taskId="task" projectId="project" focusCommentId={focusCommentId} />);
}
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

it("loads earlier pages and merges arriving messages without duplicates", async () => {
  const read = vi.spyOn(api, "getComments").mockImplementation(async (_id, cursor) => {
    if (cursor?.before) return { comments: [row(1)], has_more: false };
    if (cursor?.after) return { comments: [row(2), row(3)], has_more: false };
    return { comments: [row(2)], has_more: true };
  });
  mount();
  await screen.findByText("Message 3");
  await userEvent.click(screen.getByRole("button", { name: "Earlier messages" }));
  await screen.findByText("Message 1");
  expect(screen.getAllByText("Message 2")).toHaveLength(1);
  expect(read).toHaveBeenCalledWith("task", { before: 2 });
});

it("keeps draft and request ID on retry and sends structured mentions", async () => {
  vi.spyOn(api, "getComments").mockResolvedValue({ comments: [], has_more: false });
  const send = vi.spyOn(api, "sendComment").mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValue(row());
  mount(); await screen.findByText("No messages yet.");
  await userEvent.type(screen.getByLabelText("Message"), "Hello @Ann");
  await userEvent.click(await screen.findByRole("button", { name: "@Anna Smith" }));
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Connection lost");
  expect(screen.getByLabelText("Message")).toHaveValue("Hello ");
  const first = send.mock.calls[0];
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  await waitFor(() => expect(send).toHaveBeenCalledTimes(2));
  expect(send.mock.calls[1]).toEqual(first);
  expect(first.slice(0, 4)).toEqual(["task", "Hello ", ["member"], []]);
  await waitFor(() => expect(screen.getByLabelText("Message")).toHaveValue(""));
});

it("allows file-only messages, validates limits and disables duplicate submission", async () => {
  vi.spyOn(api, "getComments").mockResolvedValue({ comments: [], has_more: false });
  let finish: (message: api.ChatMessage) => void = () => {};
  const send = vi.spyOn(api, "sendComment").mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  mount(); await screen.findByText("No messages yet.");
  const tooBig = new File(["x"], "large.bin"); Object.defineProperty(tooBig, "size", { value: 25 * 1024 * 1024 + 1 });
  await userEvent.upload(screen.getByLabelText("Attachments"), tooBig);
  expect(screen.getByRole("alert")).toHaveTextContent("25 MB");
  expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
  const file = new File(["hello"], "notes.txt");
  await userEvent.upload(screen.getByLabelText("Attachments"), file);
  await userEvent.click(screen.getByRole("button", { name: "Send message" }));
  expect(screen.getByRole("button", { name: "Sending message" })).toBeDisabled();
  expect(send.mock.calls[0][3]).toEqual([file]);
  await act(async () => { finish(row()); });
});

it("sends with Enter and keeps Shift+Enter as a new line", async () => {
  vi.spyOn(api, "getComments").mockResolvedValue({ comments: [], has_more: false });
  const send = vi.spyOn(api, "sendComment").mockResolvedValue(row());
  mount(); await screen.findByText("No messages yet.");
  const input = screen.getByLabelText("Message");
  await userEvent.type(input, "First line{shift>}{enter}{/shift}Second line");
  expect(input).toHaveValue("First line\nSecond line");
  await userEvent.keyboard("{Enter}");
  await waitFor(() => expect(send).toHaveBeenCalledWith("task", "First line\nSecond line", [], [], expect.any(String)));
});

it("opens an inline image in a full-screen dialog and closes it with Escape", async () => {
  const imageMessage = row();
  imageMessage.attachments = [{ id: "image", filename: "screen.png", media_type: "image/png", size: 42 }];
  vi.spyOn(api, "getComments").mockResolvedValue({ comments: [imageMessage], has_more: false });
  vi.spyOn(api, "getAttachment").mockResolvedValue(new Blob(["image"]));
  vi.stubGlobal("URL", { ...URL, createObjectURL: vi.fn(() => "blob:preview"), revokeObjectURL: vi.fn() });
  mount();
  await userEvent.click(await screen.findByRole("button", { name: "Open image screen.png" }));
  const dialog = screen.getByRole("dialog", { name: "Image preview: screen.png" });
  expect(dialog).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Close image preview" })).toHaveFocus();
  await userEvent.keyboard("{Escape}");
  expect(dialog).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Open image screen.png" })).toHaveFocus();
});

it("opens an old notification target without downloading the full chat", async () => {
  const scrollIntoView = vi.fn();
  vi.stubGlobal("requestAnimationFrame", (fn: FrameRequestCallback) => { fn(0); return 1; });
  const original = HTMLElement.prototype.scrollIntoView;
  HTMLElement.prototype.scrollIntoView = scrollIntoView;
  vi.spyOn(api, "getComment").mockResolvedValue(row(10));
  const read = vi.spyOn(api, "getComments").mockImplementation(async (_id, cursor) => ({ comments: cursor?.before ? [row(9)] : [], has_more: false }));
  mount("message-10");
  expect(await screen.findByText("Message 10")).toBeInTheDocument();
  expect(read).toHaveBeenCalledWith("task");
  expect(api.getComment).toHaveBeenCalledWith("task", "message-10");
  expect(document.getElementById("comment-message-10")).toHaveClass("highlighted");
  HTMLElement.prototype.scrollIntoView = original;
  vi.unstubAllGlobals();
});

it("removes cached messages and composer when polling detects revoked access", async () => {
  vi.spyOn(api, "getComments").mockResolvedValueOnce({ comments: [row()], has_more: false }).mockRejectedValue(new api.ApiError("Not found", 404));
  mount();
  expect(await screen.findByText("Task access is no longer available.")).toBeInTheDocument();
  expect(screen.queryByText("Message 1")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Message")).not.toBeInTheDocument();
});
