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

test("ZaloBridgeServer responds to get_status request", async () => {
  const server = new ZaloBridgeServer({
    port: 3997,
    token: "",
    sessionPath: "/tmp/test-zalo-session.json",
  });

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3997");
    await new Promise((resolve) => ws.once("open", resolve));

    ws.send(JSON.stringify({ type: "get_status" }));
    const reply = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Timeout")), 1000);
      ws.once("message", (msg) => {
        clearTimeout(timer);
        resolve(JSON.parse(msg.toString()));
      });
    });
    assert.equal(reply.type, "status");
    assert.equal(reply.status, "ready_for_login");

    ws.close();
  } finally {
    await server.stop();
  }
});

test("ZaloBridgeServer dispatches send with styles and typing event to zaloApi", async () => {
  const server = new ZaloBridgeServer({
    port: 3996,
    token: "",
    sessionPath: "/tmp/test-zalo-session.json",
  });

  const sentMessages = [];
  const typingEvents = [];
  server.zaloApi = {
    getContext: () => ({ uid: "bot_123" }),
    sendMessage: async (payload, threadId, threadType) => {
      sentMessages.push({ payload, threadId, threadType });
      return { message: { msgId: 100 } };
    },
    sendTypingEvent: async (threadId, threadType) => {
      typingEvents.push({ threadId, threadType });
      return { status: 0 };
    },
  };

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3996");
    await new Promise((resolve) => ws.once("open", resolve));

    // Send typing
    ws.send(
      JSON.stringify({
        type: "typing",
        thread_id: "user_789",
        thread_type: "user",
      })
    );

    // Send styled message
    ws.send(
      JSON.stringify({
        type: "send",
        thread_id: "user_789",
        thread_type: "user",
        text: "Styled reply",
        styles: [{ start: 0, len: 6, st: "b" }],
      })
    );

    await new Promise((resolve) => setTimeout(resolve, 50));

    assert.equal(typingEvents.length, 1);
    assert.equal(typingEvents[0].threadId, "user_789");
    assert.equal(typingEvents[0].threadType, 0);

    assert.equal(sentMessages.length, 1);
    assert.equal(sentMessages[0].threadId, "user_789");
    assert.equal(sentMessages[0].payload.msg, "Styled reply");
    assert.deepEqual(sentMessages[0].payload.styles, [
      { start: 0, len: 6, st: "b" },
    ]);

    ws.close();
  } finally {
    await server.stop();
  }
});

