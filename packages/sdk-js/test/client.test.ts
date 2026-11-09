import assert from "node:assert/strict";
import { test } from "node:test";
import { createClient } from "../src/index.ts";

function fakeFetch(status = 202) {
  const calls: Array<{ url: string; body: any; headers: any }> = [];
  const f = (async (url: string, init: any) => {
    calls.push({ url, body: JSON.parse(init.body), headers: init.headers });
    return new Response(null, { status });
  }) as unknown as typeof fetch;
  return { f, calls };
}

test("batches and dedupes per user per UTC day", async () => {
  const { f, calls } = fakeFetch();
  const gm = createClient({ apiKey: "gm_pub_x", baseUrl: "http://h/", fetch: f, flushIntervalMs: 10_000 });
  for (let i = 0; i < 5; i++) gm.active("u1", { platform: "web" });
  gm.active("u2");
  gm.active("u1", {}, new Date("2099-01-02T00:00:00Z"));
  await gm.flush();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "http://h/v1/events");
  assert.equal(calls[0].headers.authorization, "Bearer gm_pub_x");
  assert.deepEqual(calls[0].body.events.map((e: any) => e.user_id), ["u1", "u2", "u1"]);
});

test("never throws and reports rejected batches via onError", async () => {
  const { f } = fakeFetch(400);
  const errors: unknown[] = [];
  const gm = createClient({ apiKey: "gm_pub_x", fetch: f, onError: (e) => errors.push(e) });
  gm.active("u1");
  await gm.flush();
  assert.equal(errors.length, 1);
});

test("disabled without api key", async () => {
  const { f, calls } = fakeFetch();
  const gm = createClient({ apiKey: "", fetch: f });
  gm.active("u1");
  await gm.shutdown();
  assert.equal(calls.length, 0);
});
