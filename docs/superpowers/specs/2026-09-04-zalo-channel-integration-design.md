# Zalo Channel Integration Design Specification

## 1. Overview & Goals

This specification details the architecture, protocol, and implementation for integrating **Zalo** (a dominant instant messaging platform in Vietnam) as a partner channel in DeepTutor.

Interaction with Zalo Web (`chat.zalo.me`) is powered by the [`zca-js`](https://github.com/cuongpt083/zca-js.git) library. Because `zca-js` is written in TypeScript/Node.js and performs specialized browser simulation and encryption (AES-CBC, ZCID, token signing, WebSocket frame decoding), the integration follows DeepTutor's established **WebSocket Bridge Sidecar** pattern (analogous to [`WhatsAppChannel`](file:///home/cuongpt/DeepTutor/deeptutor/partners/channels/whatsapp.py)).

### Goals
- Enable DeepTutor companions (Partners) to send and receive messages on Zalo (both Direct Messages and Groups).
- Support QR-code onboarding via the DeepTutor Web UI.
- Support session persistence (saving cookies/IMEI so restarts do not require re-scanning).
- Respect DeepTutor security standards (`allow_from` filtering, secret masking, isolated state dirs).
- Provide a clean, standalone Node.js bridge daemon under `bridges/zalo-bridge/`.

---

## 2. System Architecture

```
 ┌────────────────────────────────────────────────────────────┐
 │                       DeepTutor Core                       │
 │                                                            │
 │  ┌────────────────────────┐      ┌──────────────────────┐  │
 │  │      Web Frontend      │      │     FastAPI Core     │  │
 │  │ (PartnerChannels, UI)  │◄────►│ (ChannelOnboarding)  │  │
 │  └────────────────────────┘      └──────────┬───────────┘  │
 │                                             │              │
 │                                  ┌──────────▼───────────┐  │
 │                                  │     ZaloChannel      │  │
 │                                  │ (deeptutor/partners) │  │
 └──────────────────────────────────┴──────────┬───────────┴──┘
                                               │ WebSocket (JSON RPC)
                                               │ ws://localhost:3002
 ┌─────────────────────────────────────────────▼──────────────┐
 │                    Zalo Bridge Sidecar                     │
 │                   (`bridges/zalo-bridge`)                  │
 │                                                            │
 │  ┌──────────────────────────────────────────────────────┐  │
 │  │ WebSocket Server (auth, send, qr_stream, events)    │  │
 │  └──────────────────────────┬───────────────────────────┘  │
 │                             │                              │
 │  ┌──────────────────────────▼───────────────────────────┐  │
 │  │  ZCA JS Engine (`cuongpt083/zca-js`)                 │  │
 │  │  - loginQR() / loginCookie()                         │  │
 │  │  - api.listener (WebSocket zpw_ws)                   │  │
 │  │  - api.sendMessage()                                │  │
 │  └──────────────────────────┬───────────────────────────┘  │
 └─────────────────────────────┼──────────────────────────────┘
                               │ HTTPS / WSS
                               ▼
                       Zalo Web Gateway
```

### Components

1. **`bridges/zalo-bridge/`**:
   - Standalone Node.js service using `zca-js`.
   - Listens on `ws://127.0.0.1:3002` (configurable via `PORT` / `HOST`).
   - Manages Zalo connection lifecycle, credentials storage (`session.json`), and QR code generation.
   - Translates ZCA JS events into DeepTutor WebSocket bridge messages.

2. **`deeptutor/partners/channels/zalo.py`**:
   - `ZaloConfig`: Pydantic config model inheriting from `DeliveryOverrides`.
   - `ZaloChannel`: Inherits from `BaseChannel`.
   - Connects to the bridge WebSocket, dispatches `InboundMessage` to DeepTutor `MessageBus`, handles `OutboundMessage` delivery with retry policy.

3. **`deeptutor/services/partners/channel_onboarding.py`**:
   - Extends onboarding provider to support `zalo`.
   - Bridges QR login events between the Web UI and the Zalo bridge.

4. **Web UI**:
   - `web/components/partners/ChannelIcon.tsx`: Brand icon for Zalo with `#0068FF` brand color.
   - Dynamic schema forms automatically generated via `_partners_channel_schema.py`.
   - QR Onboarding Panel allows scanning QR code from phone.

---

## 3. Communication Protocol (Bridge Wire Protocol)

The bridge runs a WebSocket server. All payloads are JSON objects with a `type` field.

### A. Authentication & Handshake
1. Client (DeepTutor) connects to `ws://localhost:3002`.
2. If `bridge_token` is configured:
   - DeepTutor -> Bridge:
     ```json
     { "type": "auth", "token": "secret-token" }
     ```
   - Bridge -> DeepTutor:
     ```json
     { "type": "auth_ok" }
     ```
     *(If invalid: `{ "type": "auth_error", "message": "Invalid token" }` and closes connection with code 4401).*

### B. Status & Health
- Bridge -> DeepTutor:
  ```json
  {
    "type": "status",
    "status": "connected",
    "user_id": "1234567890",
    "display_name": "DeepTutor Assistant"
  }
  ```
  Status values: `ready_for_login`, `logging_in`, `connected`, `disconnected`, `duplicate_connection`.

### C. QR Code Login (Onboarding)
- DeepTutor -> Bridge:
  ```json
  { "type": "start_qr_login" }
  ```
- Bridge -> DeepTutor (QR Code emitted):
  ```json
  {
    "type": "qr_generated",
    "data": {
      "qr_data_url": "data:image/png;base64,iVBORw0KGgo...",
      "token": "qr-session-token",
      "expires_in": 120
    }
  }
  ```
- Bridge -> DeepTutor (User scanned on mobile phone):
  ```json
  {
    "type": "qr_scanned",
    "data": {
      "avatar": "https://avatar.zalo.me/...",
      "display_name": "Nguyen Van A"
    }
  }
  ```
- Bridge -> DeepTutor (Login completed):
  ```json
  {
    "type": "qr_success",
    "data": {
      "uid": "1234567890",
      "name": "Nguyen Van A"
    }
  }
  ```
- Bridge -> DeepTutor (Login declined or expired):
  ```json
  { "type": "qr_expired" }
  // or { "type": "qr_declined" }
  ```

### D. Inbound Messages (Bridge -> DeepTutor)
When a message arrives on Zalo:
```json
{
  "type": "message",
  "id": "msg_987654321",
  "thread_id": "thread_123456",
  "thread_type": "user",
  "sender_id": "user_112233",
  "sender_name": "Nguyen Van A",
  "content": "Explain Fourier Transform",
  "is_self": false,
  "mentions": [],
  "quote": null,
  "timestamp": 1725390000000
}
```
- For group messages: `thread_type: "group"`, `thread_id: "<groupId>"`, `sender_id: "<senderUid>"`, `mentions: [{"uid": "...", "pos": 0, "len": 5}]`.
- DeepTutor maps this to `InboundMessage(channel="zalo", sender_id=sender_id, chat_id=thread_id, content=content, metadata={...})`.

### E. Outbound Messages (DeepTutor -> Bridge)
When DeepTutor delivers an agent response:
```json
{
  "type": "send",
  "thread_id": "thread_123456",
  "thread_type": "user",
  "text": "The Fourier Transform decomposes a function of time into its frequencies...",
  "quote_id": "msg_987654321"
}
```
Bridge calls:
```typescript
api.sendMessage({ msg: text, quote: quoteObject }, thread_id, threadTypeEnum);
```

---

## 4. Configuration Schema (`ZaloConfig`)

```python
class ZaloConfig(DeliveryOverrides):
    enabled: bool = Field(default=False, description="Enable Zalo partner channel.")
    bridge_url: str = Field(default="ws://127.0.0.1:3002", description="WebSocket URL of the Zalo bridge.")
    bridge_token: str = Field(default="", description="Optional bearer token for bridge authentication.")
    allow_from: list[str] = Field(default_factory=list, description="Allowed Zalo user UIDs. '*' allows all.")
    group_policy: Literal["open", "mention", "allowlist"] = Field(
        default="mention", description="Group handling: 'open' responds to all, 'mention' requires bot mention, 'allowlist' responds only to group_allow_from."
    )
    group_allow_from: list[str] = Field(default_factory=list, description="Allowed group IDs when group_policy is 'allowlist'.")
    reply_with_quote: bool = Field(default=True, description="Quote original message when replying.")
```

---

## 5. Error Handling & Edge Cases

1. **Duplicate Web Connection (`CloseReason.DuplicateConnection = 3000`)**:
   - Zalo permits only one active Web session. If the account is opened in a desktop/web browser, Zalo drops the bot's WebSocket.
   - **Handling**: Bridge emits `{ "type": "status", "status": "duplicate_connection" }`. The channel logs an explanatory warning: `"Zalo Web was opened in another browser/app. Zalo bot listener stopped to prevent session conflict."`
2. **Reconnection Strategy**:
   - If the WebSocket connection between `ZaloChannel` and the bridge drops, `ZaloChannel` retries with exponential backoff (1s, 2s, 5s, max 10s).
   - If the bridge's connection to Zalo drops, the bridge retries using `zca-js` internal socket retries.
3. **Non-streaming Nature**:
   - Zalo does not support in-place message editing (`send_delta` is not implemented). All responses are buffered and sent as full messages upon completion or tool progress steps.
4. **Credential Isolation**:
   - Session cookies and credentials are saved per Partner workspace in `state_dir/zalo_session.json` to prevent collisions between partners.

---

## 6. Testing Strategy

1. **`tests/services/partners/test_zalo_channel.py`**:
   - Config validation and default values.
   - Connection lifecycle: Handshake, auth token verification, graceful stop.
   - Inbound message parsing: DM vs Group handling, mention detection, `allow_from` filter verification.
   - Outbound delivery: JSON payload verification, quote reply verification, error handling when disconnected.
2. **Bridge Unit/Integration Tests**:
   - Wire protocol parser tests.
   - ZCA JS event mapping tests.
