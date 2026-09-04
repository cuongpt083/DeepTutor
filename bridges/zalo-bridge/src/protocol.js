/**
 * Wire protocol helpers for Zalo Bridge <-> DeepTutor.
 */

export function formatInboundMessage(message) {
  const data = message.data || {};
  const threadType = message.type === 1 ? "group" : "user";
  const content =
    typeof data.content === "string"
      ? data.content
      : typeof data.content?.title === "string"
        ? data.content.title
        : "";

  return {
    type: "message",
    id: String(data.msgId || ""),
    thread_id: String(message.threadId || ""),
    thread_type: threadType,
    sender_id: String(data.uidFrom || message.threadId || ""),
    sender_name: String(data.dName || ""),
    content,
    is_self: Boolean(message.isSelf),
    mentions: Array.isArray(data.mentions) ? data.mentions : [],
    quote: data.quote || null,
    timestamp: Number(data.ts || Date.now()),
  };
}

export function parseOutboundMessage(raw) {
  let parsed;
  try {
    parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
  } catch {
    throw new Error("Invalid JSON payload");
  }

  if (!parsed || parsed.type !== "send") {
    throw new Error(`Expected type 'send', got '${parsed?.type}'`);
  }
  if (!parsed.thread_id || typeof parsed.text !== "string") {
    throw new Error("Missing thread_id or text in send payload");
  }

  return {
    type: "send",
    thread_id: String(parsed.thread_id),
    thread_type: parsed.thread_type === "group" ? "group" : "user",
    text: String(parsed.text),
    quote_id: parsed.quote_id ? String(parsed.quote_id) : undefined,
  };
}

export function formatStatus(status, details = {}) {
  return {
    type: "status",
    status,
    user_id: details.userId ? String(details.userId) : undefined,
    display_name: details.displayName ? String(details.displayName) : undefined,
    message: details.message ? String(details.message) : undefined,
  };
}

export function formatQrEvent(type, data = {}) {
  return {
    type,
    data: {
      qr_data_url: data.qrDataUrl,
      code: data.code,
      token: data.token,
      avatar: data.avatar,
      display_name: data.displayName,
      uid: data.uid,
      name: data.name,
    },
  };
}
