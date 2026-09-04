import test from "node:test";
import assert from "node:assert/strict";
import { WebSocket } from "ws";
import { ZaloBridgeServer } from "../src/server.js";

test("ZaloBridgeServer handles auth handshake and message dispatch", async () => {
  const server = new ZaloBridgeServer({
    port: 3999,
    token: "test-token",
    sessionPath: "/tmp/test-zalo-session.json",
  });

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3999");
    await new Promise((resolve) => ws.once("open", resolve));

    // Send valid auth
    ws.send(JSON.stringify({ type: "auth", token: "test-token" }));
    const authReply = await new Promise((resolve) =>
      ws.once("message", (msg) => resolve(JSON.parse(msg.toString())))
    );
    assert.equal(authReply.type, "auth_ok");

    // Broadcast message to connected client
    server.broadcast({ type: "status", status: "ready_for_login" });
    const statusReply = await new Promise((resolve) =>
      ws.once("message", (msg) => resolve(JSON.parse(msg.toString())))
    );
    assert.equal(statusReply.type, "status");
    assert.equal(statusReply.status, "ready_for_login");

    ws.close();
  } finally {
    await server.stop();
  }
});

test("ZaloBridgeServer rejects invalid token", async () => {
  const server = new ZaloBridgeServer({
    port: 3998,
    token: "secret-token",
  });

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3998");
    await new Promise((resolve) => ws.once("open", resolve));

    ws.send(JSON.stringify({ type: "auth", token: "wrong-token" }));
    const reply = await new Promise((resolve) =>
      ws.once("message", (msg) => resolve(JSON.parse(msg.toString())))
    );
    assert.equal(reply.type, "auth_error");

    const closeCode = await new Promise((resolve) => ws.once("close", resolve));
    assert.equal(closeCode, 4401);
  } finally {
    await server.stop();
  }
});
