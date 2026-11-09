/**
 * @growth-model/sdk — report active users to a growth-model server.
 *
 *   import { createClient } from "@growth-model/sdk";
 *   const gm = createClient({ apiKey: "gm_pub_...", baseUrl: "https://growth.example.com" });
 *   gm.active(user.id, { platform: "web", appVersion: "2.4.1" });
 *
 * Zero dependencies. Works in browsers, React Native, Node >= 18, Deno, Bun and edge runtimes.
 * Never throws into the host app, batches requests, and sends at most one event per user per UTC day.
 * Use a *publishable* (gm_pub_) key: it can only ingest, so it is safe to ship in client code.
 */

export type Metadata = Record<string, string | number | boolean | null | undefined>;

export interface ClientOptions {
  apiKey: string;
  baseUrl?: string;
  /** Max ms to wait before sending a partial batch. Default 2000. */
  flushIntervalMs?: number;
  maxBatchSize?: number;
  maxQueueSize?: number;
  maxRetries?: number;
  /** Set false to disable (e.g. in tests or when the user has opted out). */
  enabled?: boolean;
  fetch?: typeof fetch;
  onError?: (error: unknown) => void;
}

export interface ActiveEvent {
  user_id: string;
  timestamp: string;
  metadata: Metadata;
}

export interface GrowthModelClient {
  /** Record that `userId` was active now (or at `timestamp`). Cheap; call on every session/request. */
  active(userId: string, metadata?: Metadata, timestamp?: Date): void;
  /** Send everything queued. Resolves when done; never rejects. */
  flush(): Promise<void>;
  /** Flush and stop timers. */
  shutdown(): Promise<void>;
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function createClient(options: ClientOptions): GrowthModelClient {
  const baseUrl = (options.baseUrl ?? "http://localhost:8000").replace(/\/+$/, "");
  const flushIntervalMs = options.flushIntervalMs ?? 2000;
  const maxBatchSize = options.maxBatchSize ?? 100;
  const maxQueueSize = options.maxQueueSize ?? 10_000;
  const maxRetries = options.maxRetries ?? 3;
  const doFetch = options.fetch ?? globalThis.fetch?.bind(globalThis);
  const onError = options.onError ?? (() => {});
  const enabled = (options.enabled ?? true) && Boolean(options.apiKey) && Boolean(doFetch);

  let queue: ActiveEvent[] = [];
  let seenDay = "";
  const seen = new Set<string>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  let inflight: Promise<void> = Promise.resolve();

  async function send(batch: ActiveEvent[], keepalive = false): Promise<void> {
    for (let attempt = 0; attempt <= maxRetries; attempt++) {
      try {
        const res = await doFetch!(`${baseUrl}/v1/events`, {
          method: "POST",
          headers: { "content-type": "application/json", authorization: `Bearer ${options.apiKey}` },
          body: JSON.stringify({ events: batch }),
          keepalive,
        });
        if (res.ok) return;
        if (res.status < 500 && res.status !== 429) {
          onError(new Error(`growth-model: events rejected (${res.status})`));
          return;
        }
      } catch (err) {
        if (attempt === maxRetries) onError(err);
      }
      await sleep(Math.min(30_000, 500 * 2 ** attempt));
    }
  }

  function schedule() {
    if (timer === undefined) timer = setTimeout(() => void flush(), flushIntervalMs);
  }

  function flush(keepalive = false): Promise<void> {
    if (timer !== undefined) {
      clearTimeout(timer);
      timer = undefined;
    }
    while (queue.length) {
      const batch = queue.splice(0, maxBatchSize);
      inflight = inflight.then(() => send(batch, keepalive)).catch(onError);
    }
    return inflight;
  }

  function active(userId: string, metadata: Metadata = {}, timestamp: Date = new Date()) {
    try {
      if (!enabled || !userId) return;
      const iso = timestamp.toISOString();
      const day = iso.slice(0, 10);
      if (day > seenDay) {
        seen.clear();
        seenDay = day;
      }
      const key = `${userId}\u0000${day}`;
      if (seen.has(key)) return;
      seen.add(key);
      if (queue.length >= maxQueueSize) return;
      queue.push({ user_id: String(userId), timestamp: iso, metadata });
      if (queue.length >= maxBatchSize) void flush();
      else schedule();
    } catch (err) {
      onError(err);
    }
  }

  // Best-effort delivery when a browser tab is hidden or closed.
  const g = globalThis as { addEventListener?: (t: string, f: () => void) => void };
  if (enabled && typeof g.addEventListener === "function") {
    g.addEventListener("pagehide", () => void flush(true));
  }

  return {
    active,
    flush: () => flush(),
    shutdown: async () => {
      await flush();
    },
  };
}
