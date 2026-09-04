import assert from "node:assert/strict";
import test from "node:test";

import {
  connectLightRagServer,
  probeLightRagServer,
} from "../features/knowledge/api/client";

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(
  handler: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>,
): () => void {
  const original = globalThis.fetch;
  (globalThis as { fetch: typeof fetch }).fetch = handler;
  return () => {
    (globalThis as { fetch: typeof fetch }).fetch = original;
  };
}

test("probeLightRagServer sends workspace in request payload", async () => {
  const captured: { input: string; init?: RequestInit } = { input: "" };
  const restore = stubFetch(async (input, init) => {
    captured.input = String(input);
    captured.init = init;
    return jsonResponse(200, {
      ok: true,
      base_url: "http://localhost:9621",
    });
  });
  try {
    const res = await probeLightRagServer({
      serverUrl: "http://localhost:9621",
      apiKey: "secret",
      workspace: "my-workspace",
    });
    assert.equal(res.ok, true);
    assert.ok(captured.init?.body);
    const body = JSON.parse(String(captured.init.body));
    assert.equal(body.server_url, "http://localhost:9621");
    assert.equal(body.api_key, "secret");
    assert.equal(body.workspace, "my-workspace");
  } finally {
    restore();
  }
});

test("connectLightRagServer sends workspace in request payload", async () => {
  const captured: { input: string; init?: RequestInit } = { input: "" };
  const restore = stubFetch(async (input, init) => {
    captured.input = String(input);
    captured.init = init;
    return jsonResponse(200, {
      status: "connected",
      name: "remote-ws",
      server_url: "http://localhost:9621",
      workspace: "my-workspace",
      rag_provider: "lightrag-server",
    });
  });
  try {
    const res = await connectLightRagServer({
      name: "remote-ws",
      serverUrl: "http://localhost:9621",
      apiKey: "secret",
      workspace: "my-workspace",
      mode: "mix",
    });
    assert.equal(res.status, "connected");
    assert.ok(captured.init?.body);
    const body = JSON.parse(String(captured.init.body));
    assert.equal(body.name, "remote-ws");
    assert.equal(body.server_url, "http://localhost:9621");
    assert.equal(body.api_key, "secret");
    assert.equal(body.workspace, "my-workspace");
    assert.equal(body.search_mode, "mix");
  } finally {
    restore();
  }
});
