import test from "node:test";
import assert from "node:assert/strict";
import {
  formatInboundMessage,
  parseOutboundMessage,
  formatStatus,
  formatQrEvent,
} from "../src/protocol.js";

test("formatInboundMessage formats user direct message correctly", () => {
  const zcaMsg = {
    type: 0, // ThreadType.User
    threadId: "user_456",
    isSelf: false,
    data: {
      msgId: "msg_111",
      uidFrom: "user_456",
      dName: "Alice",
      content: "Hello from Zalo",
      ts: "1725390000000",
    },
  };

  const wire = formatInboundMessage(zcaMsg);
  assert.equal(wire.type, "message");
  assert.equal(wire.id, "msg_111");
  assert.equal(wire.thread_id, "user_456");
  assert.equal(wire.thread_type, "user");
  assert.equal(wire.sender_id, "user_456");
  assert.equal(wire.sender_name, "Alice");
  assert.equal(wire.content, "Hello from Zalo");
  assert.equal(wire.is_self, false);
});

test("formatInboundMessage formats group message with mentions", () => {
  const zcaMsg = {
    type: 1, // ThreadType.Group
    threadId: "group_789",
    isSelf: false,
    data: {
      msgId: "msg_222",
      uidFrom: "user_123",
      dName: "Bob",
      content: "@Bot tell me a joke",
      mentions: [{ uid: "bot_999", pos: 0, len: 4 }],
      ts: "1725390010000",
    },
  };

  const wire = formatInboundMessage(zcaMsg);
  assert.equal(wire.thread_type, "group");
  assert.equal(wire.thread_id, "group_789");
  assert.equal(wire.sender_id, "user_123");
  assert.deepEqual(wire.mentions, [{ uid: "bot_999", pos: 0, len: 4 }]);
});

test("parseOutboundMessage validates send payload", () => {
  const raw = JSON.stringify({
    type: "send",
    thread_id: "user_456",
    thread_type: "user",
    text: "Bot reply",
    quote_id: "msg_111",
  });

  const parsed = parseOutboundMessage(raw);
  assert.equal(parsed.thread_id, "user_456");
  assert.equal(parsed.thread_type, "user");
  assert.equal(parsed.text, "Bot reply");
  assert.equal(parsed.quote_id, "msg_111");
});

test("formatStatus formats status event", () => {
  const status = formatStatus("connected", {
    userId: "bot_999",
    displayName: "Tutor Bot",
  });
  assert.equal(status.type, "status");
  assert.equal(status.status, "connected");
  assert.equal(status.user_id, "bot_999");
  assert.equal(status.display_name, "Tutor Bot");
});

test("formatQrEvent formats qr code payload", () => {
  const qr = formatQrEvent("qr_generated", {
    qrDataUrl: "data:image/png;base64,xyz",
    token: "tok_1",
  });
  assert.equal(qr.type, "qr_generated");
  assert.equal(qr.data.qr_data_url, "data:image/png;base64,xyz");
  assert.equal(qr.data.token, "tok_1");
});
