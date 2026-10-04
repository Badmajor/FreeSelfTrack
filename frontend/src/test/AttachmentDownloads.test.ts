import { afterEach, expect, it, vi } from "vitest";
import { getAttachment } from "../api";

afterEach(() => { vi.unstubAllGlobals(); vi.useRealTimers(); });

it("queues downloads until the preceding body is consumed", async () => {
  let finish!: (blob: Blob) => void;
  const body = new Promise<Blob>((resolve) => { finish = resolve; });
  const fetch = vi.fn().mockResolvedValueOnce({ ok: true, status: 200, blob: () => body })
    .mockResolvedValue(new Response("second"));
  vi.stubGlobal("fetch", fetch);
  const first = getAttachment("first", true);
  const second = getAttachment("second", true);
  await vi.waitFor(() => expect(fetch).toHaveBeenCalledTimes(1));
  finish(new Blob(["first"]));
  await first;
  expect((await second).size).toBe(6);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it("retries temporary download limits using Retry-After", async () => {
  vi.useFakeTimers();
  const fetch = vi.fn().mockResolvedValueOnce(new Response("busy", { status: 429, headers: { "Retry-After": "2" } }))
    .mockResolvedValue(new Response("image"));
  vi.stubGlobal("fetch", fetch);
  const result = getAttachment("image", true);
  await vi.advanceTimersByTimeAsync(1999);
  expect(fetch).toHaveBeenCalledTimes(1);
  await vi.advanceTimersByTimeAsync(1);
  expect((await result).size).toBe(5);
});

it("does not retry denied attachments or block subsequent downloads", async () => {
  const fetch = vi.fn().mockResolvedValueOnce(new Response("hidden", { status: 404 }))
    .mockResolvedValue(new Response("next"));
  vi.stubGlobal("fetch", fetch);
  await expect(getAttachment("hidden")).rejects.toMatchObject({ status: 404 });
  expect((await getAttachment("next")).size).toBe(4);
  expect(fetch).toHaveBeenCalledTimes(2);
});
