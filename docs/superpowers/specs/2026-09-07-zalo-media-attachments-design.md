# Zalo Channel Media & Image Attachments Design Specification

## 1. Overview & Goals

This specification defines the architecture, wire protocol updates, and channel implementation for handling incoming media (images, photos, and document files) from **Zalo** to **DeepTutor**.

Previously, when a user sent an image via the Zalo client (`chat.zalo.me` or mobile), the Zalo Bridge and Zalo Channel only extracted text content. Because image metadata and download URLs were omitted from the inbound wire payload, `InboundMessage.media` remained empty, preventing LLMs (e.g. Gemini, GPT-4o, Claude) from receiving vision inputs.

### Goals
- Enable DeepTutor companions (Partners) on Zalo to receive and process photos/images (`chat.photo`) via multimodal LLM capabilities.
- Support document attachments (`share.file` such as PDF and text files) for partner context and RAG extraction.
- Extract image captions and URLs reliably in `bridges/zalo-bridge/src/protocol.js`.
- Download attachments securely in `deeptutor/partners/channels/zalo.py` into isolated partner media directories (`media_dir`).
- Default empty user messages with attachments to standard prompts (`"Please analyze the attached image(s)."`), consistent with Web channel behavior.
- Ensure thorough unit tests for both Node.js protocol parsing and Python channel message handling.

---

## 2. Architecture & Data Flow

```
┌────────────────────────────────────────────────────────┐
│                      Zalo User                         │
│             (Sends photo or document)                  │
└──────────────────────────┬─────────────────────────────┘
                           │ Zalo Protocol (WSS / HTTPS)
                           ▼
┌────────────────────────────────────────────────────────┐
│                 Zalo Bridge Sidecar                    │
│                (`bridges/zalo-bridge`)                 │
│                                                        │
│  - `api.listener` receives `UserMessage` / `GroupMsg`  │
│  - `formatInboundMessage` inspects `msgType` & content │
│  - Extracts `attachments: [{ type, url, filename }]`   │
└──────────────────────────┬─────────────────────────────┘
                           │ WebSocket (JSON RPC)
                           │ `attachments` field in payload
                           ▼
┌────────────────────────────────────────────────────────┐
│                   DeepTutor Backend                    │
│                      (Python)                          │
│                                                        │
│  ┌──────────────────────────────────────────────────┐  │
│  │     `ZaloChannel` (`channels/zalo.py`)           │  │
│  │  - Parses `attachments` from bridge event        │  │
│  │  - Downloads files via `httpx` into `media_dir`  │  │
│  │  - Sets fallback prompt if content is empty      │  │
│  │  - Calls `_handle_message(..., media=paths)`     │  │
│  └───────────────────────┬──────────────────────────┘  │
│                          │                             │
│                          ▼ InboundMessage              │
│  ┌──────────────────────────────────────────────────┐  │
│  │     `PartnerRuntime` (`partners/runtime.py`)     │  │
│  │  - Calls `_attachments_from_media(msg.media)`    │  │
│  │  - Wraps image in `Attachment(type="image")`     │  │
│  │  - Appends to `UnifiedContext.attachments`       │  │
│  └───────────────────────┬──────────────────────────┘  │
│                          │                             │
│                          ▼ UnifiedContext              │
│  ┌──────────────────────────────────────────────────┐  │
│  │                 LLM Model                        │  │
│  │  - Multimodal Vision analysis (Gemini / Claude)  │  │
│  └──────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Design

### 3.1. Bridge Wire Protocol (`bridges/zalo-bridge/src/protocol.js`)

In Zalo protocol (`zca-js`), incoming media messages have specific `msgType` values and object structures in `data.content`:

1. **Photo messages (`msgType === "chat.photo"` or `content.thumb` / `content.href` present):**
   - High-resolution URL: `data.content.hdUrl || data.content.normalUrl || data.content.href || data.content.thumb || data.content.url`.
   - Caption / Text: `data.content.description || data.content.desc || data.content.title || (typeof data.content === "string" ? data.content : "")`.
   - Filename fallback: derived from URL or `"photo.jpg"`.
   - Attachment item: `{ type: "image", url: String(url), filename: String(filename) }`.

2. **File messages (`msgType === "share.file"`):**
   - File download URL: `data.content.href || data.content.url`.
   - Original filename: `data.content.title || data.content.fileName || "document"`.
   - File size: `Number(data.content.fileSize || data.content.size || 0)`.
   - Attachment item: `{ type: "file", url: String(url), filename: String(filename), size: Number(size) }`.

3. **Inbound Wire Payload Schema:**
```json
{
  "type": "message",
  "id": "msg_123456789",
  "thread_id": "thread_987654",
  "thread_type": "user",
  "sender_id": "user_112233",
  "sender_name": "Nguyen Van A",
  "content": "Check this nutrition chart",
  "attachments": [
    {
      "type": "image",
      "url": "https://res-zalo.zadn.vn/photo/...",
      "filename": "chart.jpg"
    }
  ],
  "is_self": false,
  "mentions": [],
  "quote": null,
  "timestamp": 1725390000000
}
```

### 3.2. Channel Adapter Implementation (`deeptutor/partners/channels/zalo.py`)

1. **HTTP Client Lifecycle:**
   - Initialize `self._http = httpx.AsyncClient(timeout=30.0, follow_redirects=True)` in `ZaloChannel.start()`.
   - Ensure clean shutdown of `self._http` in `ZaloChannel.stop()`.

2. **Attachment Downloader (`_download_attachments`):**
   - Maximum attachment size limit: `MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024` (50MB).
   - Target directory: `self.media_dir()` (isolated per partner workspace).
   - Download headers:
     ```python
     headers = {
         "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
         "Referer": "https://chat.zalo.me/",
     }
     ```
   - Filename sanitization: `uuid4().hex[:12] + "_" + safe_filename(filename)`.
   - Concurrency: Download multiple attachments concurrently using `asyncio.gather`.

3. **Content Fallback:**
   - If `not content.strip()` and `attachments`:
     - If all attachments are images: `content = "Please analyze the attached image(s)."`
     - Otherwise: `content = "Please use the attached file(s)."`

4. **Message Forwarding:**
   - Call `await self._handle_message(sender_id=sender_id, chat_id=chat_id, content=content, media=media_paths, metadata=metadata)`.

---

## 4. Error Handling & Edge Cases

1. **Network Failure / CDN Expiration:**
   - If an image URL fails to download (e.g. 404, 403, network timeout), log warning and continue without crashing the turn.
   - If all attachments fail to download and `content` was empty, preserve error notice in content so the partner informs the user.
2. **Unsupported / Malformed URLs:**
   - Validate URL scheme (`http://` or `https://`) before making requests. Ignore invalid or local URL schemes.
3. **Large File Attacks:**
   - Reject attachments exceeding `MAX_ATTACHMENT_BYTES`. Stream downloads or check `Content-Length` header before buffering full payloads into RAM.
4. **Group Mention & Quoting with Media:**
   - Ensure group mention filtering and quote replies continue to work seamlessly when messages contain images.

---

## 5. Testing Strategy

1. **Node.js Bridge Protocol Tests (`bridges/zalo-bridge/test/protocol.test.js`):**
   - Test formatting of `chat.photo` with explicit caption.
   - Test formatting of `chat.photo` without caption (extracts image URL, empty text).
   - Test formatting of `share.file` (extracts file URL, filename, and size).
   - Test formatting of regular text message (attachments is empty array).
2. **Python Channel Tests (`tests/services/partners/test_zalo_channel.py`):**
   - Test inbound message with image attachment downloads to `media_dir` and passes `media` to `_handle_message`.
   - Test empty content message with image receives fallback prompt `"Please analyze the attached image(s)."`.
   - Test download failure does not block inbound message dispatch.
   - Test oversized attachment skipping.
