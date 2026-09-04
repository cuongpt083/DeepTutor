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

test("ZaloBridgeServer sends connected status with userId and displayName on connection", async () => {
  const server = new ZaloBridgeServer({
    port: 3994,
    token: "",
    sessionPath: "/tmp/test-zalo-session.json",
  });
  server.zaloApi = {
    getOwnId: () => "bot_555",
    getContext: () => ({ uid: "bot_555" }),
  };
  server.botDisplayName = "NutriTech Bot";

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3994");
    const statusMsg = await new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Timeout")), 1000);
      ws.once("message", (msg) => {
        clearTimeout(timer);
        resolve(JSON.parse(msg.toString()));
      });
    });

    assert.equal(statusMsg.type, "status");
    assert.equal(statusMsg.status, "connected");
    assert.equal(statusMsg.user_id, "bot_555");
    assert.equal(statusMsg.display_name, "NutriTech Bot");

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

test("ZaloBridgeServer resolves cached quote for group and retries without quote on failure", async () => {
  const server = new ZaloBridgeServer({
    port: 3995,
    token: "",
    sessionPath: "/tmp/test-zalo-session.json",
  });

  // Pre-populate cached message
  server.recentMessages.set("msg_orig_1", {
    msgId: "msg_orig_1",
    cliMsgId: "cli_1",
    uidFrom: "user_author",
    content: "Original question",
    ts: 1725390000000,
  });

  let callCount = 0;
  const attempts = [];
  server.zaloApi = {
    getContext: () => ({ uid: "bot_123" }),
    sendMessage: async (payload, threadId, threadType) => {
      callCount++;
      attempts.push({ payload: { ...payload }, threadId, threadType });
      if (payload.quote) {
        throw new Error("Invalid quote content");
      }
      return { message: { msgId: 200 } };
    },
  };

  await server.start();

  try {
    const ws = new WebSocket("ws://127.0.0.1:3995");
    await new Promise((resolve) => ws.once("open", resolve));

    // Send message to group quoting msg_orig_1
    ws.send(
      JSON.stringify({
        type: "send",
        thread_id: "group_555",
        thread_type: "group",
        text: "Answer in group",
        quote_id: "msg_orig_1",
      })
    );

    await new Promise((resolve) => setTimeout(resolve, 50));

    // Attempt 1 had quote and failed; Attempt 2 succeeded without quote
    assert.equal(callCount, 2);
    assert.equal(attempts[0].threadType, 1);
    assert.ok(attempts[0].payload.quote);
    assert.equal(attempts[0].payload.quote.content, "Original question");

    assert.equal(attempts[1].threadType, 1);
    assert.equal(attempts[1].payload.quote, undefined);
    assert.equal(attempts[1].payload.msg, "Answer in group");

    ws.close();
  } finally {
    await server.stop();
  }
});


