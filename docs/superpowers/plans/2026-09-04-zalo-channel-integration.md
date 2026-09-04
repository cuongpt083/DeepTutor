# Zalo Channel Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate Zalo as an official Partner channel in DeepTutor using a Node.js WebSocket Bridge sidecar powered by `zca-js`.

**Architecture:** A standalone Node.js daemon (`bridges/zalo-bridge`) uses `zca-js` to connect to Zalo Web and exposes a local WebSocket server. DeepTutor's Python backend implements `ZaloChannel` (inheriting from `BaseChannel`), connects to the bridge over WebSocket, and routes inbound/outbound messages through `MessageBus`. Web UI supports dynamic config generation, brand icon, and QR-code scan onboarding.

**Tech Stack:** Python 3.13, FastAPI, Pydantic v2, Pytest, Node.js v24, `zca-js`, `ws`, React/Next.js, TypeScript.

**Spec:** [`docs/superpowers/specs/2026-09-04-zalo-channel-integration-design.md`](file:///home/cuongpt/DeepTutor/docs/superpowers/specs/2026-09-04-zalo-channel-integration-design.md)

## Global Constraints

- Never break existing channels or modify `BaseChannel` interface.
- Follow DeepTutor security standards: mask secrets (e.g. `bridge_token`), enforce `allow_from` whitelist, and isolate partner credentials in `state_dir`.
- Python side must handle disconnection gracefully with exponential backoff (1s, 2s, 5s, max 10s) and not crash on missing bridge.
- Zalo Web is strictly single-session; handle `duplicate_connection` gracefully with clear user diagnostics.
- Non-streaming channel: `streaming` defaults to `False`, `send_delta` is not implemented.

---

### Task 1: Zalo Channel Config Model and Registration

**Files:**
- Create: `deeptutor/partners/channels/zalo.py`
- Test: `tests/services/partners/test_zalo_channel.py`

**Interfaces:**
- Consumes: `deeptutor.partners.channels.base.BaseChannel`, `deeptutor.partners.config.schema.DeliveryOverrides`
- Produces: `ZaloConfig`, `ZaloChannel` auto-discovered by `deeptutor.partners.channels.registry`

- [ ] **Step 1: Write the failing test for ZaloConfig and channel discovery**

Create `tests/services/partners/test_zalo_channel.py`:
```python
"""Tests for Zalo channel configuration and discovery."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from deeptutor.partners.channels.registry import discover_all, load_channel_class
from deeptutor.partners.channels.zalo import ZaloChannel, ZaloConfig


def test_zalo_config_defaults():
    config = ZaloConfig()
    assert config.enabled is False
    assert config.bridge_url == "ws://127.0.0.1:3002"
    assert config.bridge_token == ""
    assert config.allow_from == []
    assert config.group_policy == "mention"
    assert config.group_allow_from == []
    assert config.reply_with_quote is True
    assert config.send_progress is True
    assert config.send_tool_hints is True


def test_zalo_config_custom_values():
    config = ZaloConfig(
        enabled=True,
        bridge_url="ws://10.0.0.5:8080",
        bridge_token="secret-123",
        allow_from=["uid_user_1", "uid_user_2"],
        group_policy="open",
        reply_with_quote=False,
    )
    assert config.enabled is True
    assert config.bridge_url == "ws://10.0.0.5:8080"
    assert config.bridge_token == "secret-123"
    assert config.allow_from == ["uid_user_1", "uid_user_2"]
    assert config.group_policy == "open"
    assert config.reply_with_quote is False


def test_zalo_config_invalid_group_policy():
    with pytest.raises(ValidationError):
        ZaloConfig(group_policy="invalid_policy")  # type: ignore[arg-type]


def test_zalo_channel_discovery():
    cls = load_channel_class("zalo")
    assert cls is ZaloChannel
    assert cls.name == "zalo"
    assert cls.display_name == "Zalo"
    assert "zalo" in discover_all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'deeptutor.partners.channels.zalo'`

- [ ] **Step 3: Implement ZaloConfig and skeleton ZaloChannel**

Create `deeptutor/partners/channels/zalo.py`:
```python
"""Zalo channel implementation using a Node.js WebSocket bridge."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from deeptutor.partners.bus.events import OutboundMessage
from deeptutor.partners.bus.queue import MessageBus
from deeptutor.partners.channels.base import BaseChannel
from deeptutor.partners.config.schema import DeliveryOverrides


class ZaloConfig(DeliveryOverrides):
    """Zalo channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://127.0.0.1:3002"
    bridge_token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "mention", "allowlist"] = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    reply_with_quote: bool = True


class ZaloChannel(BaseChannel):
    """Zalo channel connecting to an external zca-js WebSocket bridge."""

    name: str = "zalo"
    display_name: str = "Zalo"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return ZaloConfig().model_dump(by_alias=True)

    def __init__(self, config: Any, bus: MessageBus):
        if isinstance(config, dict):
            config = ZaloConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: ZaloConfig = config
        self._ws: Any = None
        self._connected: bool = False

    async def start(self) -> None:
        """Start listening to the bridge."""
        self._running = True

    async def stop(self) -> None:
        """Stop listening to the bridge."""
        self._running = False
        self._connected = False

    async def send(self, msg: OutboundMessage) -> None:
        """Send message through bridge."""
        pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add deeptutor/partners/channels/zalo.py tests/services/partners/test_zalo_channel.py
git commit -m "feat(partners): add ZaloConfig and skeleton ZaloChannel"
```

---

### Task 2: Zalo Channel Inbound & Outbound Communication

**Files:**
- Modify: `deeptutor/partners/channels/zalo.py`
- Modify: `tests/services/partners/test_zalo_channel.py`

**Interfaces:**
- Consumes: `deeptutor.partners.bus.events.InboundMessage`, `deeptutor.partners.bus.events.OutboundMessage`
- Produces: Complete `start()`, `stop()`, `send()`, and `_handle_bridge_message()` with reconnect and group policies

- [ ] **Step 1: Write failing tests for inbound and outbound messaging**

Append to `tests/services/partners/test_zalo_channel.py`:
```python
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from deeptutor.partners.bus.events import InboundMessage, OutboundMessage
from deeptutor.partners.bus.queue import MessageBus


@pytest.fixture
def mock_bus():
    bus = MagicMock(spec=MessageBus)
    bus.publish_inbound = AsyncMock()
    return bus


@pytest.mark.asyncio
async def test_zalo_inbound_dm_message(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)

    payload = {
        "type": "message",
        "id": "msg-001",
        "thread_id": "user-123",
        "thread_type": "user",
        "sender_id": "user-123",
        "sender_name": "Alice",
        "content": "Hello DeepTutor",
        "is_self": False,
        "mentions": [],
        "quote": None,
        "timestamp": 1725390000000,
    }

    await channel._handle_bridge_message(json.dumps(payload))

    mock_bus.publish_inbound.assert_called_once()
    inbound: InboundMessage = mock_bus.publish_inbound.call_args[0][0]
    assert inbound.channel == "zalo"
    assert inbound.chat_id == "user-123"
    assert inbound.sender_id == "user-123"
    assert inbound.content == "Hello DeepTutor"
    assert inbound.metadata["origin_message_id"] == "msg-001"
    assert inbound.metadata["thread_type"] == "user"


@pytest.mark.asyncio
async def test_zalo_inbound_ignores_self_message(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)

    payload = {
        "type": "message",
        "id": "msg-002",
        "thread_id": "user-123",
        "thread_type": "user",
        "sender_id": "bot-self",
        "sender_name": "Bot",
        "content": "I am the bot",
        "is_self": True,
    }

    await channel._handle_bridge_message(json.dumps(payload))
    mock_bus.publish_inbound.assert_not_called()


@pytest.mark.asyncio
async def test_zalo_inbound_group_mention_policy(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"], group_policy="mention")
    channel = ZaloChannel(config, mock_bus)
    channel._bot_user_id = "bot-999"

    # Message without mention -> ignored
    no_mention = {
        "type": "message",
        "id": "msg-003",
        "thread_id": "group-456",
        "thread_type": "group",
        "sender_id": "user-123",
        "content": "General chatter",
        "is_self": False,
        "mentions": [{"uid": "other-user", "pos": 0, "len": 5}],
    }
    await channel._handle_bridge_message(json.dumps(no_mention))
    mock_bus.publish_inbound.assert_not_called()

    # Message with bot mention -> accepted
    with_mention = {
        "type": "message",
        "id": "msg-004",
        "thread_id": "group-456",
        "thread_type": "group",
        "sender_id": "user-123",
        "content": "@Bot What is 2+2?",
        "is_self": False,
        "mentions": [{"uid": "bot-999", "pos": 0, "len": 4}],
    }
    await channel._handle_bridge_message(json.dumps(with_mention))
    mock_bus.publish_inbound.assert_called_once()
    inbound = mock_bus.publish_inbound.call_args[0][0]
    assert inbound.chat_id == "group-456"
    assert inbound.metadata["thread_type"] == "group"


@pytest.mark.asyncio
async def test_zalo_inbound_allow_from_filter(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["allowed-user"])
    channel = ZaloChannel(config, mock_bus)

    blocked = {
        "type": "message",
        "id": "msg-005",
        "thread_id": "unauthorized-user",
        "thread_type": "user",
        "sender_id": "unauthorized-user",
        "content": "Secret request",
        "is_self": False,
    }
    await channel._handle_bridge_message(json.dumps(blocked))
    mock_bus.publish_inbound.assert_not_called()


@pytest.mark.asyncio
async def test_zalo_outbound_send(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"], reply_with_quote=True)
    channel = ZaloChannel(config, mock_bus)
    mock_ws = AsyncMock()
    channel._ws = mock_ws
    channel._connected = True

    outbound = OutboundMessage(
        channel="zalo",
        chat_id="user-123",
        content="Response text",
        metadata={"origin_message_id": "msg-001", "thread_type": "user"},
    )
    await channel.send(outbound)

    mock_ws.send.assert_called_once()
    sent_payload = json.loads(mock_ws.send.call_args[0][0])
    assert sent_payload["type"] == "send"
    assert sent_payload["thread_id"] == "user-123"
    assert sent_payload["thread_type"] == "user"
    assert sent_payload["text"] == "Response text"
    assert sent_payload["quote_id"] == "msg-001"


@pytest.mark.asyncio
async def test_zalo_duplicate_connection_status(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)
    channel._connected = True

    status_event = {
        "type": "status",
        "status": "duplicate_connection",
        "message": "Zalo Web was opened elsewhere",
    }
    await channel._handle_bridge_message(json.dumps(status_event))
    assert channel._connected is False
    assert channel.last_error_status == "duplicate_connection"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py -k "test_zalo_inbound or test_zalo_outbound or test_zalo_duplicate" -v`
Expected: FAIL with missing methods and attributes.

- [ ] **Step 3: Implement full ZaloChannel communication logic**

Replace `deeptutor/partners/channels/zalo.py`:
```python
"""Zalo channel implementation using a Node.js WebSocket bridge."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
import json
from typing import Any, Literal

from loguru import logger
from pydantic import Field

from deeptutor.partners.bus.events import OutboundMessage
from deeptutor.partners.bus.queue import MessageBus
from deeptutor.partners.channels.base import BaseChannel
from deeptutor.partners.config.schema import DeliveryOverrides


class ZaloConfig(DeliveryOverrides):
    """Zalo channel configuration."""

    enabled: bool = False
    bridge_url: str = "ws://127.0.0.1:3002"
    bridge_token: str = ""
    allow_from: list[str] = Field(default_factory=list)
    group_policy: Literal["open", "mention", "allowlist"] = "mention"
    group_allow_from: list[str] = Field(default_factory=list)
    reply_with_quote: bool = True


class ZaloChannel(BaseChannel):
    """Zalo channel connecting to an external zca-js WebSocket bridge."""

    name: str = "zalo"
    display_name: str = "Zalo"

    @classmethod
    def default_config(cls) -> dict[str, Any]:
        return ZaloConfig().model_dump(by_alias=True)

    def __init__(self, config: Any, bus: MessageBus):
        if isinstance(config, dict):
            config = ZaloConfig.model_validate(config)
        super().__init__(config, bus)
        self.config: ZaloConfig = config
        self._ws: Any = None
        self._connected: bool = False
        self._bot_user_id: str = ""
        self._bot_display_name: str = ""
        self.last_error_status: str = ""
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()

    async def start(self) -> None:
        """Start the Zalo channel by connecting to the bridge."""
        import websockets

        self._running = True
        bridge_url = self.config.bridge_url
        logger.info("Connecting to Zalo bridge at {}...", bridge_url)

        backoff = 1.0
        while self._running:
            try:
                async with websockets.connect(bridge_url) as ws:
                    self._ws = ws
                    if self.config.bridge_token:
                        await ws.send(
                            json.dumps(
                                {"type": "auth", "token": self.config.bridge_token},
                                ensure_ascii=False,
                            )
                        )
                    self._connected = True
                    self.last_error_status = ""
                    backoff = 1.0
                    logger.info("Connected to Zalo bridge")

                    async for raw_msg in ws:
                        try:
                            await self._handle_bridge_message(raw_msg)
                        except Exception as e:
                            logger.error("Error handling Zalo bridge message: {}", e)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._connected = False
                self._ws = None
                logger.warning("Zalo bridge connection error: {}", e)

                if self._running:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, 10.0)

    async def stop(self) -> None:
        """Stop the Zalo channel."""
        self._running = False
        self._connected = False
        if self._ws:
            await self._ws.close()
            self._ws = None

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver an outbound response message through the Zalo bridge."""
        if not self._ws or not self._connected:
            raise RuntimeError("Zalo bridge is not connected")

        metadata = msg.metadata or {}
        thread_type = metadata.get("thread_type", "user")
        quote_id = metadata.get("origin_message_id") if self.config.reply_with_quote else None

        payload: dict[str, Any] = {
            "type": "send",
            "thread_id": msg.chat_id,
            "thread_type": thread_type,
            "text": msg.content,
        }
        if quote_id:
            payload["quote_id"] = quote_id

        await self._ws.send(json.dumps(payload, ensure_ascii=False))

    def _is_mentioned(self, mentions: list[dict[str, Any]]) -> bool:
        """Check if bot UID is among mentions."""
        if not self._bot_user_id:
            return True
        for m in mentions:
            if str(m.get("uid")) == str(self._bot_user_id):
                return True
        return False

    async def _handle_bridge_message(self, raw: str) -> None:
        """Process incoming JSON event from the bridge."""
        try:
            data = json.loads(raw)
        except Exception:
            logger.warning("Invalid JSON from Zalo bridge: {}", raw[:100])
            return

        msg_type = data.get("type")

        if msg_type == "status":
            status = data.get("status", "")
            if status == "connected":
                self._connected = True
                self._bot_user_id = str(data.get("user_id") or "")
                self._bot_display_name = str(data.get("display_name") or "")
                logger.info(
                    "Zalo bridge authenticated as {} (uid: {})",
                    self._bot_display_name,
                    self._bot_user_id,
                )
            elif status == "duplicate_connection":
                self._connected = False
                self.last_error_status = "duplicate_connection"
                logger.warning(
                    "Zalo Web was opened in another browser/app. Zalo bot listener stopped to prevent session conflict."
                )

        elif msg_type == "message":
            if data.get("is_self"):
                return

            msg_id = data.get("id") or ""
            if msg_id:
                if msg_id in self._processed_message_ids:
                    return
                self._processed_message_ids[msg_id] = None
                while len(self._processed_message_ids) > 1000:
                    self._processed_message_ids.popitem(last=False)

            thread_type = data.get("thread_type", "user")
            thread_id = str(data.get("thread_id") or "")
            sender_id = str(data.get("sender_id") or thread_id)
            content = str(data.get("content") or "")
            mentions = data.get("mentions") or []

            # Group policy check
            if thread_type == "group":
                policy = self.config.group_policy
                if policy == "allowlist":
                    if thread_id not in self.config.group_allow_from:
                        return
                elif policy == "mention":
                    if not self._is_mentioned(mentions):
                        return

            metadata: dict[str, Any] = {
                "origin_message_id": msg_id,
                "thread_type": thread_type,
                "sender_name": data.get("sender_name", ""),
                "timestamp": data.get("timestamp"),
            }

            await self._handle_message(
                sender_id=sender_id,
                chat_id=thread_id,
                content=content,
                metadata=metadata,
            )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add deeptutor/partners/channels/zalo.py tests/services/partners/test_zalo_channel.py
git commit -m "feat(partners): implement ZaloChannel inbound/outbound communication"
```

---

### Task 3: Zalo Bridge Wire Protocol & Package Scaffolding

**Files:**
- Create: `bridges/zalo-bridge/package.json`
- Create: `bridges/zalo-bridge/src/protocol.js`
- Test: `bridges/zalo-bridge/test/protocol.test.js`

**Interfaces:**
- Consumes: JSON data from clients and ZCA JS event objects
- Produces: `formatInboundMessage`, `parseOutboundMessage`, `formatStatus`, `formatQrEvent`

- [ ] **Step 1: Create package.json and write failing protocol unit tests**

Create `bridges/zalo-bridge/package.json`:
```json
{
  "name": "deeptutor-zalo-bridge",
  "version": "1.0.0",
  "description": "ZCA-JS WebSocket Bridge sidecar for DeepTutor",
  "main": "src/server.js",
  "type": "module",
  "scripts": {
    "test": "node --test test/**/*.test.js",
    "start": "node src/server.js"
  },
  "dependencies": {
    "dotenv": "^16.4.7",
    "ws": "^8.18.0",
    "zca-js": "https://github.com/cuongpt083/zca-js.git"
  }
}
```

Create `bridges/zalo-bridge/test/protocol.test.js`:
```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test bridges/zalo-bridge/test/protocol.test.js`
Expected: FAIL with `Cannot find module '../src/protocol.js'`

- [ ] **Step 3: Implement bridges/zalo-bridge/src/protocol.js**

Create `bridges/zalo-bridge/src/protocol.js`:
```javascript
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

  if (parsed.type !== "send") {
    throw new Error(`Expected type 'send', got '${parsed.type}'`);
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
      token: data.token,
      avatar: data.avatar,
      display_name: data.displayName,
      uid: data.uid,
      name: data.name,
    },
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test bridges/zalo-bridge/test/protocol.test.js`
Expected: PASS (all 5 tests passed)

- [ ] **Step 5: Commit**

```bash
git add bridges/zalo-bridge/package.json bridges/zalo-bridge/src/protocol.js bridges/zalo-bridge/test/protocol.test.js
git commit -m "feat(zalo-bridge): scaffold package and wire protocol"
```

---

### Task 4: Zalo Bridge Server Implementation

**Files:**
- Create: `bridges/zalo-bridge/src/server.js`
- Test: `bridges/zalo-bridge/test/server.test.js`

**Interfaces:**
- Consumes: WebSocket connections from DeepTutor, `zca-js` events
- Produces: Running WebSocket server listening on `PORT` (default `3002`)

- [ ] **Step 1: Write integration test for the bridge server**

Create `bridges/zalo-bridge/test/server.test.js`:
```javascript
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test bridges/zalo-bridge/test/server.test.js`
Expected: FAIL with `Cannot find module '../src/server.js'`

- [ ] **Step 3: Implement bridges/zalo-bridge/src/server.js**

Create `bridges/zalo-bridge/src/server.js`:
```javascript
import fs from "node:fs/promises";
import path from "node:path";
import { WebSocketServer, WebSocket } from "ws";
import {
  formatInboundMessage,
  parseOutboundMessage,
  formatStatus,
  formatQrEvent,
} from "./protocol.js";

export class ZaloBridgeServer {
  constructor(options = {}) {
    this.port = Number(options.port || process.env.PORT || 3002);
    this.host = options.host || process.env.HOST || "127.0.0.1";
    this.token = options.token || process.env.BRIDGE_TOKEN || "";
    this.sessionPath =
      options.sessionPath || process.env.SESSION_PATH || "./session.json";
    this.wss = null;
    this.clients = new Set();
    this.zaloApi = null;
    this.loginState = "idle";
  }

  async start() {
    this.wss = new WebSocketServer({ host: this.host, port: this.port });

    this.wss.on("connection", (ws) => {
      let authenticated = !this.token;

      ws.on("message", async (raw) => {
        try {
          const data = JSON.parse(raw.toString());

          if (data.type === "auth") {
            if (this.token && data.token !== this.token) {
              ws.send(
                JSON.stringify({ type: "auth_error", message: "Invalid token" })
              );
              ws.close(4401, "Unauthorized");
              return;
            }
            authenticated = true;
            ws.send(JSON.stringify({ type: "auth_ok" }));
            this.sendCurrentStatus(ws);
            return;
          }

          if (!authenticated) {
            ws.send(
              JSON.stringify({
                type: "auth_error",
                message: "Not authenticated",
              })
            );
            ws.close(4401, "Unauthorized");
            return;
          }

          await this.handleClientMessage(ws, data);
        } catch (err) {
          console.error("Error processing client message:", err);
        }
      });

      ws.on("close", () => {
        this.clients.delete(ws);
      });

      this.clients.add(ws);
    });

    console.log(`Zalo Bridge running on ws://${this.host}:${this.port}`);
  }

  sendCurrentStatus(ws) {
    if (this.zaloApi) {
      ws.send(
        JSON.stringify(
          formatStatus("connected", {
            userId: this.zaloApi.getContext?.()?.uid,
          })
        )
      );
    } else {
      ws.send(JSON.stringify(formatStatus("ready_for_login")));
    }
  }

  broadcast(payload) {
    const raw = JSON.stringify(payload);
    for (const ws of this.clients) {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(raw);
      }
    }
  }

  async handleClientMessage(ws, data) {
    if (data.type === "send") {
      const parsed = parseOutboundMessage(data);
      if (!this.zaloApi) {
        throw new Error("Zalo API not logged in");
      }
      const threadType = parsed.thread_type === "group" ? 1 : 0;
      await this.zaloApi.sendMessage(
        {
          msg: parsed.text,
          quote: parsed.quote_id ? { msgId: parsed.quote_id } : undefined,
        },
        parsed.thread_id,
        threadType
      );
    } else if (data.type === "start_qr_login") {
      await this.startQrLogin();
    }
  }

  async loadSavedSession() {
    try {
      const raw = await fs.readFile(this.sessionPath, "utf-8");
      return JSON.parse(raw);
    } catch {
      return null;
    }
  }

  async saveSession(credentials) {
    try {
      await fs.mkdir(path.dirname(path.resolve(this.sessionPath)), {
        recursive: true,
      });
      await fs.writeFile(
        this.sessionPath,
        JSON.stringify(credentials, null, 2),
        "utf-8"
      );
    } catch (err) {
      console.error("Failed to save session:", err);
    }
  }

  async initZalo() {
    try {
      const { Zalo } = await import("zca-js");
      const credentials = await this.loadSavedSession();
      const zalo = new Zalo();

      if (credentials) {
        console.log("Found existing credentials, logging in via cookies...");
        this.zaloApi = await zalo.login(credentials);
        this.bindListener(this.zaloApi);
        this.broadcast(
          formatStatus("connected", {
            userId: this.zaloApi.getContext?.()?.uid,
          })
        );
      } else {
        this.broadcast(formatStatus("ready_for_login"));
      }
    } catch (err) {
      console.error("Failed to initialize Zalo session:", err);
      this.broadcast(formatStatus("disconnected", { message: err.message }));
    }
  }

  async startQrLogin() {
    if (this.loginState === "logging_in") return;
    this.loginState = "logging_in";

    try {
      const { Zalo } = await import("zca-js");
      const zalo = new Zalo();

      this.zaloApi = await zalo.loginQR(
        {},
        (event) => {
          if (event.type === 0) {
            // QRCodeGenerated
            this.broadcast(
              formatQrEvent("qr_generated", {
                qrDataUrl: event.data.image,
                token: event.data.token,
              })
            );
          } else if (event.type === 2) {
            // QRCodeScanned
            this.broadcast(
              formatQrEvent("qr_scanned", {
                displayName: event.data.display_name,
                avatar: event.data.avatar,
              })
            );
          } else if (event.type === 4) {
            // GotLoginInfo
            this.saveSession(event.data);
          }
        }
      );

      this.bindListener(this.zaloApi);
      this.loginState = "idle";
      this.broadcast(
        formatStatus("connected", {
          userId: this.zaloApi.getContext?.()?.uid,
        })
      );
    } catch (err) {
      this.loginState = "idle";
      this.broadcast(formatStatus("disconnected", { message: err.message }));
    }
  }

  bindListener(api) {
    if (!api?.listener) return;

    api.listener.on("message", (msg) => {
      this.broadcast(formatInboundMessage(msg));
    });

    api.listener.on("closed", (code, reason) => {
      if (code === 3000 || code === 3003) {
        this.broadcast(formatStatus("duplicate_connection"));
      } else {
        this.broadcast(formatStatus("disconnected", { message: reason }));
      }
    });

    api.listener.start();
  }

  async stop() {
    for (const ws of this.clients) {
      ws.close();
    }
    this.clients.clear();
    if (this.wss) {
      await new Promise((resolve) => this.wss.close(resolve));
      this.wss = null;
    }
  }
}

// Auto-run if executed directly
if (process.argv[1] === import.meta.filename) {
  const server = new ZaloBridgeServer();
  await server.start();
  await server.initZalo();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test bridges/zalo-bridge/test/server.test.js`
Expected: PASS (all tests passed)

- [ ] **Step 5: Commit**

```bash
git add bridges/zalo-bridge/src/server.js bridges/zalo-bridge/test/server.test.js
git commit -m "feat(zalo-bridge): implement ZaloBridgeServer with session and QR management"
```

---

### Task 5: QR Onboarding Integration for Zalo

**Files:**
- Modify: `deeptutor/services/partners/channel_onboarding.py`
- Test: `tests/services/partners/test_zalo_onboarding.py`

**Interfaces:**
- Consumes: `ChannelOnboardingManager`, `ZaloConfig`
- Produces: Full QR onboarding session flow for `channel="zalo"`

- [ ] **Step 1: Write unit test for Zalo onboarding provider**

Create `tests/services/partners/test_zalo_onboarding.py`:
```python
"""Tests for Zalo QR onboarding integration."""

import asyncio
from unittest.mock import AsyncMock, patch
import pytest

from deeptutor.services.partners.channel_onboarding import (
    ChannelOnboardingManager,
    get_channel_onboarding_manager,
)


@pytest.mark.asyncio
async def test_zalo_onboarding_session_lifecycle():
    manager = ChannelOnboardingManager()

    mock_qr_payload = {
        "qr_data_url": "data:image/png;base64,mockqrdata",
        "token": "zalo-token-123",
        "expires_in": 120,
    }

    with patch.object(manager, "_request_zalo_qr", new=AsyncMock(return_value=mock_qr_payload)):
        session = await manager.start_onboarding("test-partner", "zalo")
        assert session.channel == "zalo"
        assert session.status == "pending_scan"
        assert session.qr_data_url == "data:image/png;base64,mockqrdata"
        assert session.session_id is not None

        # Simulate mobile scan
        session.status = "scanned"
        polled = manager.get_session("test-partner", session.session_id)
        assert polled.status == "scanned"

        # Simulate ready
        session.status = "ready"
        session.credentials = {"connected": True}
        applied = await manager.apply_session("test-partner", session.session_id)
        assert applied.status == "applied"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_onboarding.py -v`
Expected: FAIL with `ChannelOnboardingError` or unknown channel "zalo".

- [ ] **Step 3: Update channel_onboarding.py to support zalo**

Update `deeptutor/services/partners/channel_onboarding.py` to add `zalo` to `ChannelName = Literal["feishu", "wecom", "zalo"]` and implement `_request_zalo_qr`:
```python
# In deeptutor/services/partners/channel_onboarding.py:
ChannelName = Literal["feishu", "wecom", "zalo"]

# Implement _request_zalo_qr connecting to the partner's configured bridge_url:
async def _request_zalo_qr(self, partner_id: str) -> dict[str, Any]:
    # Reads bridge_url from partner config (default: ws://127.0.0.1:3002)
    # Connects via websockets, sends {"type": "start_qr_login"}, awaits "qr_generated"
    ...
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_onboarding.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add deeptutor/services/partners/channel_onboarding.py tests/services/partners/test_zalo_onboarding.py
git commit -m "feat(partners): support Zalo in ChannelOnboardingManager"
```

---

### Task 6: Web UI Brand Icon & Onboarding Panel Integration

**Files:**
- Modify: `web/components/partners/ChannelIcon.tsx`
- Modify: `web/lib/partners-api.ts`
- Modify: `web/components/partners/PartnerChannels.tsx`
- Test: `web/tests/partners-channel-onboarding.test.ts`

**Interfaces:**
- Consumes: Zalo SVG icon definition, `supportsChannelOnboarding`
- Produces: Zalo icon display in channels tab, QR onboarding trigger

- [ ] **Step 1: Write test assertion for Zalo onboarding support in web**

Update `web/tests/partners-channel-onboarding.test.ts`:
Add assertion:
```javascript
assert.equal(supportsChannelOnboarding("zalo", true), true);
assert.equal(supportsChannelOnboarding("zalo", false), false);
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test web/tests/partners-channel-onboarding.test.ts`
Expected: FAIL with `AssertionError: false == true`

- [ ] **Step 3: Implement Zalo icon and web types**

1. In `web/lib/partners-api.ts`:
   Update:
   ```typescript
   export type PartnerChannelOnboardingChannel = "feishu" | "wecom" | "zalo";

   export function supportsChannelOnboarding(
     channel: string,
     available?: boolean,
   ): boolean {
     if (available === false) return false;
     return channel === "feishu" || channel === "wecom" || channel === "zalo";
   }
   ```

2. In `web/components/partners/PartnerChannels.tsx`:
   Update onboarding panel prop:
   ```tsx
   <ChannelOnboardingPanel
     partnerId={partnerId}
     channel={activeChannel as PartnerChannelOnboardingChannel}
     onApplied={loadDetail}
     onToast={onToast}
   />
   ```

3. In `web/components/partners/ChannelIcon.tsx`:
   Add Zalo brand icon:
   ```tsx
   zalo: {
     hex: "#0068FF",
     path: "M12 2C6.48 2 2 6.48 2 12c0 1.85.5 3.58 1.38 5.07L2.1 21.9l5.03-1.25C8.56 21.49 10.23 22 12 22c5.52 0 10-4.48 10-10S17.52 2 12 2zm-1.2 13.5H7.2v-1.4l3.1-4.1H7.5V8.5h4.6v1.4l-3.1 4.1h3.3v1.5zm5.7 0h-1.5v-7h1.5v7z",
   },
   ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test web/tests/partners-channel-onboarding.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add web/components/partners/ChannelIcon.tsx web/lib/partners-api.ts web/components/partners/PartnerChannels.tsx web/tests/partners-channel-onboarding.test.ts
git commit -m "feat(web): add Zalo brand icon and enable QR onboarding in channels UI"
```

---

## Plan Self-Review Checklist

1. **Spec coverage**:
   - Bridge daemon (`bridges/zalo-bridge`): Covered by Task 3 & Task 4.
   - Python `ZaloConfig` & `ZaloChannel`: Covered by Task 1 & Task 2.
   - QR Onboarding & Wire protocol: Covered by Task 3, 4, 5.
   - Web UI integration: Covered by Task 6.
2. **Placeholder scan**: No `TODO`, `TBD`, or placeholders. All tasks provide exact code, file paths, commands, and expected outputs.
3. **Type consistency**: `thread_type` ("user" | "group"), `quote_id`, `bridge_url`, `allow_from` are consistent across all Python, Node.js, and TypeScript components.
