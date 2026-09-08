# Zalo Channel Media & Image Attachments Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable DeepTutor Zalo partner channel to receive, download, and forward incoming images (`chat.photo`) and document attachments (`share.file`) so that LLMs can process them via multimodal vision and RAG.

**Architecture:** In the Node.js bridge (`protocol.js`), inspect `msgType` and `data.content` to extract attachment URLs, filenames, and captions into an `attachments` list in the inbound message event. In the Python channel adapter (`zalo.py`), use `httpx` to download media files into `self.media_dir()`, supply a fallback user prompt if text is empty, and pass `media=media_paths` into `_handle_message()`.

**Tech Stack:** Node.js (v20+), JavaScript, Python 3.13, `httpx`, `pytest`, `pytest-asyncio`.

**Spec:** [`docs/superpowers/specs/2026-09-07-zalo-media-attachments-design.md`](file:///home/cuongpt/DeepTutor/docs/superpowers/specs/2026-09-07-zalo-media-attachments-design.md)

## Global Constraints

- Never commit credentials, tokens, or temporary media files to git.
- Adhere to existing wire protocol JSON format (`type: "message"`).
- Keep attachment downloads strictly contained within `self.media_dir()` per partner workspace.
- Enforce `MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024` (50MB) limit on downloaded files.
- Follow TDD: write failing unit tests before modifying implementation code.

---

### Task 1: Node.js Zalo Bridge Attachment Extraction

**Files:**
- Modify: `bridges/zalo-bridge/src/protocol.js:5-28`
- Test: `bridges/zalo-bridge/test/protocol.test.js`

**Interfaces:**
- Consumes: `zcaMsg` object from `zca-js` with fields: `type` (ThreadType), `threadId`, `data` (which includes `msgType`, `content`, `dName`, `uidFrom`, `msgId`, `ts`, `mentions`, `quote`).
- Produces: JSON wire object returned by `formatInboundMessage(message)` with:
  - `attachments`: `Array<{ type: "image" | "file", url: string, filename: string, size?: number }>`
  - `content`: `string` (caption or text content, trimmed)

- [ ] **Step 1: Write failing unit tests in `bridges/zalo-bridge/test/protocol.test.js`**

Add tests for:
1. Direct photo message (`chat.photo`) with caption.
2. Photo message (`chat.photo`) without caption (extracts `attachments` with `type: "image"` and image URL, content is empty string).
3. Document file message (`share.file`) with title, href, and fileSize.
4. Normal text message (ensuring `attachments` is an empty array `[]`).

```javascript
test("formatInboundMessage extracts photo attachment with caption", () => {
  const zcaMsg = {
    type: 0,
    threadId: "user_456",
    isSelf: false,
    data: {
      msgId: "msg_photo_1",
      msgType: "chat.photo",
      uidFrom: "user_456",
      dName: "Alice",
      content: {
        href: "https://res-zalo.zadn.vn/photo/sample_hd.jpg",
        thumb: "https://res-zalo.zadn.vn/photo/sample_thumb.jpg",
        description: "What food is this?",
      },
      ts: "1725390000000",
    },
  };

  const wire = formatInboundMessage(zcaMsg);
  assert.equal(wire.type, "message");
  assert.equal(wire.content, "What food is this?");
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "image");
  assert.equal(wire.attachments[0].url, "https://res-zalo.zadn.vn/photo/sample_hd.jpg");
  assert.equal(wire.attachments[0].filename, "sample_hd.jpg");
});

test("formatInboundMessage extracts photo attachment without caption", () => {
  const zcaMsg = {
    type: 0,
    threadId: "user_456",
    isSelf: false,
    data: {
      msgId: "msg_photo_2",
      msgType: "chat.photo",
      uidFrom: "user_456",
      dName: "Alice",
      content: {
        normalUrl: "https://res-zalo.zadn.vn/photo/normal.png",
      },
      ts: "1725390000000",
    },
  };

  const wire = formatInboundMessage(zcaMsg);
  assert.equal(wire.content, "");
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "image");
  assert.equal(wire.attachments[0].url, "https://res-zalo.zadn.vn/photo/normal.png");
});

test("formatInboundMessage extracts document attachment from share.file", () => {
  const zcaMsg = {
    type: 1,
    threadId: "group_789",
    isSelf: false,
    data: {
      msgId: "msg_file_1",
      msgType: "share.file",
      uidFrom: "user_123",
      dName: "Bob",
      content: {
        title: "nutrition_plan.pdf",
        href: "https://d-zalo.zadn.vn/file/nutrition_plan.pdf",
        fileSize: 1048576,
      },
      ts: "1725390000000",
    },
  };

  const wire = formatInboundMessage(zcaMsg);
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "file");
  assert.equal(wire.attachments[0].filename, "nutrition_plan.pdf");
  assert.equal(wire.attachments[0].url, "https://d-zalo.zadn.vn/file/nutrition_plan.pdf");
  assert.equal(wire.attachments[0].size, 1048576);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test test/protocol.test.js` in `bridges/zalo-bridge`
Expected: FAIL (because `wire.attachments` is undefined).

- [ ] **Step 3: Update `formatInboundMessage` in `bridges/zalo-bridge/src/protocol.js`**

Implement attachment and caption parsing in `formatInboundMessage`:
- Parse `data.content` if string contains JSON.
- Detect `chat.photo` or presence of image URLs (`hdUrl`, `normalUrl`, `href`, `thumb`, `url`).
- Extract caption from `description`, `desc`, `title`, or string `content`.
- Detect `share.file` and extract filename, URL, and size.
- Return `attachments` array in wire payload.

```javascript
export function formatInboundMessage(message) {
  const data = message.data || {};
  const threadType = message.type === 1 ? "group" : "user";
  const msgType = String(data.msgType || "");

  let rawContent = data.content;
  if (typeof rawContent === "string" && rawContent.startsWith("{") && rawContent.endsWith("}")) {
    try {
      rawContent = JSON.parse(rawContent);
    } catch {
      // keep raw string
    }
  }

  const attachments = [];
  let content = "";

  if (typeof rawContent === "string") {
    content = rawContent;
  } else if (rawContent && typeof rawContent === "object") {
    // Extract caption / text
    if (typeof rawContent.description === "string" && rawContent.description.trim()) {
      content = rawContent.description;
    } else if (typeof rawContent.desc === "string" && rawContent.desc.trim()) {
      content = rawContent.desc;
    } else if (typeof rawContent.title === "string" && rawContent.title.trim()) {
      content = rawContent.title;
    }

    // Extract photo attachment
    if (msgType === "chat.photo" || rawContent.thumb || rawContent.hdUrl || rawContent.normalUrl) {
      const imgUrl = rawContent.hdUrl || rawContent.normalUrl || rawContent.href || rawContent.thumb || rawContent.url;
      if (imgUrl && typeof imgUrl === "string") {
        let filename = "photo.jpg";
        try {
          const parsedPath = new URL(imgUrl).pathname;
          const base = parsedPath.split("/").pop();
          if (base && /\.(jpg|jpeg|png|webp|gif)$/i.test(base)) {
            filename = base;
          }
        } catch {}
        attachments.push({
          type: "image",
          url: imgUrl,
          filename,
        });
      }
    } else if (msgType === "share.file" || rawContent.fileSize || rawContent.size) {
      // Extract file attachment
      const fileUrl = rawContent.href || rawContent.url;
      if (fileUrl && typeof fileUrl === "string") {
        const filename = String(rawContent.title || rawContent.fileName || "document");
        const size = Number(rawContent.fileSize || rawContent.size || 0);
        attachments.push({
          type: "file",
          url: fileUrl,
          filename,
          ...(size > 0 ? { size } : {}),
        });
      }
    }
  }

  return {
    type: "message",
    id: String(data.msgId || ""),
    thread_id: String(message.threadId || ""),
    thread_type: threadType,
    sender_id: String(data.uidFrom || message.threadId || ""),
    sender_name: String(data.dName || ""),
    content: content.trim(),
    attachments,
    is_self: Boolean(message.isSelf),
    mentions: Array.isArray(data.mentions) ? data.mentions : [],
    quote: data.quote || null,
    timestamp: Number(data.ts || Date.now()),
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test test/protocol.test.js` in `bridges/zalo-bridge`
Expected: All tests pass.

- [ ] **Step 5: Commit changes**

```bash
git add bridges/zalo-bridge/src/protocol.js bridges/zalo-bridge/test/protocol.test.js
git commit -m "feat(zalo-bridge): extract photo and document attachments in inbound messages"
```

---

### Task 2: Zalo Channel Adapter Media Download & Dispatch in Python

**Files:**
- Modify: `deeptutor/partners/channels/zalo.py`
- Test: `tests/services/partners/test_zalo_channel.py`

**Interfaces:**
- Consumes: bridge message JSON with optional `attachments: list[dict]`
- Produces: downloads media files to `self.media_dir()`, defaults empty prompt, and forwards `media=media_paths` into `self._handle_message(sender_id, chat_id, content, media=media_paths, metadata=metadata)`.

- [ ] **Step 1: Write failing unit tests in `tests/services/partners/test_zalo_channel.py`**

Add tests for:
1. `test_zalo_inbound_message_with_image_attachment`: verify image download into `self.media_dir()`, `inbound.media` contains local file path, and `inbound.content` has prompt.
2. `test_zalo_inbound_image_without_text_sets_default_prompt`: verify empty text with image gets `"Please analyze the attached image(s)."`.
3. `test_zalo_inbound_download_failure_graceful`: verify that when download fails, message is still dispatched without unhandled exception.

```python
@pytest.mark.asyncio
async def test_zalo_inbound_message_with_image_attachment(mock_bus, tmp_path, monkeypatch):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)
    channel.partner_id = "test_partner"
    monkeypatch.setattr(channel, "media_dir", lambda *a: tmp_path)

    fake_image_bytes = b"\x89PNG\r\n\x1a\nfake_png_data"
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.content = fake_image_bytes
    mock_resp.raise_for_status = MagicMock()

    mock_http = AsyncMock()
    mock_http.get = AsyncMock(return_value=mock_resp)
    channel._http = mock_http

    payload = {
        "type": "message",
        "id": "msg-img-1",
        "thread_id": "user-123",
        "thread_type": "user",
        "sender_id": "user-123",
        "content": "",
        "attachments": [
            {
                "type": "image",
                "url": "https://res-zalo.zadn.vn/photo/plate.png",
                "filename": "plate.png",
            }
        ],
        "is_self": False,
    }

    await channel._handle_bridge_message(json.dumps(payload))

    mock_bus.publish_inbound.assert_called_once()
    inbound: InboundMessage = mock_bus.publish_inbound.call_args[0][0]
    assert inbound.chat_id == "user-123"
    assert inbound.content == "Please analyze the attached image(s)."
    assert len(inbound.media) == 1
    downloaded_file = Path(inbound.media[0])
    assert downloaded_file.exists()
    assert downloaded_file.read_bytes() == fake_image_bytes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py -k "test_zalo_inbound_message_with_image_attachment"`
Expected: FAIL.

- [ ] **Step 3: Implement media download in `deeptutor/partners/channels/zalo.py`**

1. Add `import httpx` and `from uuid import uuid4`.
2. Define `MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024`.
3. In `ZaloChannel.__init__`: initialize `self._http: httpx.AsyncClient | None = None`.
4. In `ZaloChannel.start()`: initialize `self._http = httpx.AsyncClient(timeout=30.0, follow_redirects=True)` if None.
5. In `ZaloChannel.stop()`: close `self._http` if open.
6. Implement `_download_attachments(self, attachments: list[dict[str, Any]]) -> list[str]`.
7. In `_handle_bridge_message`:
   - Download attachments to `media_paths`.
   - If `not content.strip()` and `attachments`: default prompt.
   - Pass `media=media_paths` into `self._handle_message`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py`
Expected: All tests pass (14 existing + new attachment tests).

- [ ] **Step 5: Commit changes**

```bash
git add deeptutor/partners/channels/zalo.py tests/services/partners/test_zalo_channel.py
git commit -m "feat(zalo): support downloading and forwarding incoming media attachments"
```

---

### Task 3: Full Test Suite Verification & Regressions

**Files:**
- Test: `bridges/zalo-bridge/test/protocol.test.js`
- Test: `tests/services/partners/test_zalo_channel.py`
- Test: `tests/partners/test_zalo_formatter.py`

- [ ] **Step 1: Run all Node.js bridge tests**

Run: `node --test test/*.test.js` in `bridges/zalo-bridge`
Expected: All unit tests pass.

- [ ] **Step 2: Run all Zalo Python channel tests**

Run: `/home/cuongpt/DeepTutor/.venv/bin/pytest tests/services/partners/test_zalo_channel.py tests/partners/test_zalo_formatter.py`
Expected: All tests pass.

- [ ] **Step 3: Run git diff / status check**

Verify no lint errors, no stray files, and clean git status.
