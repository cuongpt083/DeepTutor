# Zalo Quoted Media & Attachment Fallback Design Specification

## 1. Overview & Goals

This specification defines the architecture, wire protocol updates, and channel implementation for extracting and processing media attachments (images, photos, documents) from **quoted / referenced messages** in the Zalo companion channel.

### Problem Statement
In Zalo (especially in group chats), users commonly send photos or documents as standalone messages without mentioning the bot. Later, the user replies/quotes that media message and mentions the bot (e.g., *"@Bot hãy phân tích hình ảnh này"*).
Under the current implementation:
1. The initial standalone photo message is discarded by the group policy (`group_policy="mention"`) because the bot was not mentioned.
2. The subsequent quote message is received as a text message (`msgType: "webchat"`). The bridge only extracts attachments from `data.content` (which is the user's text prompt), leaving `attachments: []`.
3. The channel adapter receives no attachments (`media: []`), causing the bot to respond that it cannot see any attached image.

### Goals
- Extract quoted media attachments in the Node.js bridge when top-level message attachments are absent.
- Implement a two-tier extraction strategy:
  1. **Tier 1 (Cache lookup):** Lookup quoted message ID (`quote.globalMsgId`, `quote.cliMsgId`, `quote.msgId`) in `this.recentMessages`. If found, extract attachments from cached message content.
  2. **Tier 2 (Quote payload parse):** If not found in cache, parse `quote.attach` and `quote.cliMsgType` directly (`cliMsgType: 32` for `chat.photo`, `46` for `share.file`).
- Ensure Python channel adapter (`zalo.py`) strips bot mention cleanly and downloads quoted attachments into `media_dir`.
- Ensure standard prompt fallback (`"Please analyze the attached image(s)."`) if user only mentions the bot on a quoted image without additional text.
- Comprehensive unit tests across both Node.js bridge protocol and Python channel adapter.

---

## 2. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────┐
│                      Zalo Group                        │
│ 1. User sends photo (no mention)                       │
│ 2. User quotes photo: "@DeepTutor hãy giải bài này"    │
└──────────────────────────┬─────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Zalo Bridge Sidecar                    │
│                (`bridges/zalo-bridge`)                 │
│                                                        │
│  - Stores msg 1 in `recentMessages` cache              │
│  - Receives msg 2 with `data.quote`                    │
│  - `formatInboundMessage(msg, recentMessages)`         │
│    - Top-level `attachments` is empty                  │
│    - Finds msg 1 in `recentMessages` (Tier 1)          │
│      or parses `quote.attach` (Tier 2)                 │
│    - Extracts `{ type: "image", url, filename }`       │
│    - Adds to `wireMessage.attachments`                 │
└──────────────────────────┬─────────────────────────────┘
                           │ WebSocket (JSON RPC)
                           │ `attachments` populated
                           ▼
┌────────────────────────────────────────────────────────┐
│                   DeepTutor Backend                    │
│                      (Python)                          │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │     `ZaloChannel` (`channels/zalo.py`)           │  │
│  │  - Detects bot mention in text/quote             │  │
│  │  - Downloads attachments to `media_dir`          │  │
│  │  - Cleans `@DeepTutor` from prompt text          │  │
│  │  - Invokes `_handle_message(content, media)`     │  │
│  └───────────────────────┬──────────────────────────┘  │
│                          │
│                          ▼ InboundMessage
│  ┌──────────────────────────────────────────────────┐  │
│  │     `PartnerRuntime` (`partners/runtime.py`)     │  │
│  │  - Forwards `media` to LLM multimodal capability │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Design

### 3.1 Node.js Bridge (`bridges/zalo-bridge`)

#### Helper: `extractAttachments(rawContent, msgType)`
Refactor top-level attachment parsing into a reusable function:
- Accepts `rawContent` (string JSON or object) and optional `msgType`.
- Checks for image indicators: `msgType === "chat.photo"`, or URLs in `hdUrl`, `oriUrl`, `normalUrl`, `href`, `thumb`, `thumbUrl`, `url`.
- Checks for file indicators: `msgType === "share.file"`, or presence of `fileSize`/`size` and `href`/`url`.
- Returns `Array<{ type: "image" | "file", url: string, filename: string, size?: number }>`.

#### Quoted Attachment Extraction in `formatInboundMessage(message, recentMessages)`
When top-level `attachments.length === 0` and `data.quote` is present:
1. **Tier 1 - Cache Lookup:**
   - Candidate keys: `quote.globalMsgId`, `quote.cliMsgId`, `quote.msgId`.
   - If `recentMessages` map is provided and contains the key:
     - Retrieve `cached = recentMessages.get(key)`.
     - Extract attachments: `extractAttachments(cached.content, cached.msgType)`.
2. **Tier 2 - Payload Fallback:**
   - If Tier 1 produced no attachments, inspect `quote.attach`:
     - If `quote.attach` is a string starting with `{`: try `JSON.parse(quote.attach)`.
     - Determine message type from `quote.cliMsgType` (32 -> `"chat.photo"`, 46 -> `"share.file"`).
     - Run `extractAttachments(parsedAttach, msgType)`.
     - If `quote.attach` is a direct URL:
       - If `quote.cliMsgType === 32` or URL contains image extension:
         create `{ type: "image", url: quote.attach, filename: "photo.jpg" }`.
       - If `quote.cliMsgType === 46` or URL contains document extension:
         create `{ type: "file", url: quote.attach, filename: quote.msg || "document" }`.
3. If attachments found, populate `wireMessage.attachments`.

#### Server Integration (`server.js`)
Pass `this.recentMessages` into `formatInboundMessage`:
```javascript
this.broadcast(formatInboundMessage(msg, this.recentMessages));
```

### 3.2 Python Channel Adapter (`deeptutor/partners/channels/zalo.py`)

#### Mention Stripping & Prompt Resolution
When user sends `@BotName hãy giải bài này`:
- Strip `@bot_name` or `@bot_display_name` pattern (case-insensitive) from `content`.
- If cleaned content is empty (e.g., user only replied with `@BotName` to the quoted photo) and `attachments` are present:
  - Default prompt to: `"Please analyze the attached image(s)."` (or `"Please use the attached file(s)."`).
- If cleaned content is not empty:
  - Keep cleaned user prompt (e.g., `"hãy giải bài này"`).
- `_download_attachments()` processes all attachments in `data.get("attachments")`, writing local files to `media_paths`.
- Pass `media=media_paths` to `_handle_message()`.

---

## 4. Test Specifications

### Bridge Tests (`bridges/zalo-bridge/test/protocol.test.js`)
1. Quoted photo resolved via `recentMessages` cache lookup.
2. Quoted photo resolved via `quote.attach` JSON payload when not in cache.
3. Quoted photo resolved via `quote.attach` URL string when not in cache.
4. Quoted file resolved via `quote.attach` with `cliMsgType: 46`.
5. Quoted plain text message (no attachments added).
6. Message without quote (existing behavior preserved).

### Channel Tests (`tests/services/partners/test_zalo_channel.py`)
1. Inbound group message quoting a photo with text mention `@Bot hãy đọc ảnh này` -> passes `media` with downloaded image path and clean content.
2. Inbound group message quoting a photo with only `@Bot` mention -> sets fallback prompt `"Please analyze the attached image(s)."` and passes `media`.
3. Inbound group message quoting a document -> passes `media` with downloaded document path.
