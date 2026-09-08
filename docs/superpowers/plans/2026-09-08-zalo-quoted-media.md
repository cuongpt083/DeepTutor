# Zalo Quoted Media & Attachment Fallback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable DeepTutor Zalo companion channel to extract, download, and forward media attachments (images/photos and documents) from quoted/referenced messages in group and 1:1 chats.

**Architecture:** In `bridges/zalo-bridge/src/protocol.js`, refactor attachment extraction into a reusable helper `extractAttachments()`. When formatting an inbound message whose top-level `attachments` is empty and `data.quote` is present, resolve quoted media via a 2-tier fallback: Tier 1 checks `recentMessages` cache in `server.js` by quoted message IDs, Tier 2 parses `quote.attach` and `quote.cliMsgType`. In `deeptutor/partners/channels/zalo.py`, strip bot mentions cleanly from user prompts, trigger fallback prompt when text is empty, and download quoted attachments into `media_dir` before forwarding to the agent runtime.

**Tech Stack:** Node.js (v20+), JavaScript, Python 3.13, `pytest`, `pytest-asyncio`, `httpx`.

**Spec:** [`docs/superpowers/specs/2026-09-08-zalo-quoted-media-design.md`](file:///home/cuongpt/DeepTutor/docs/superpowers/specs/2026-09-08-zalo-quoted-media-design.md)

## Global Constraints

- Never commit credentials, tokens, or temporary media files to git.
- Adhere to the existing wire protocol JSON format (`type: "message"`).
- Keep attachment downloads strictly contained within `self.media_dir()` per partner workspace.
- Enforce `MAX_ATTACHMENT_BYTES = 50 * 1024 * 1024` (50MB) limit on downloaded files.
- Follow TDD: write failing unit tests before writing implementation code.

---

### Task 1: Node.js Bridge Quoted Media Extraction

**Files:**
- Modify: `bridges/zalo-bridge/src/protocol.js:5-103`
- Modify: `bridges/zalo-bridge/src/server.js:400-405`
- Test: `bridges/zalo-bridge/test/protocol.test.js`

**Interfaces:**
- Consumes:
  - `message`: `zca-js` inbound message object containing `data.quote` (with `globalMsgId`, `cliMsgId`, `cliMsgType`, `attach`, `msg`) and `data.content`.
  - `recentMessages` (optional `Map<string, any>`): cached recent messages indexed by message ID.
- Produces:
  - `formatInboundMessage(message, recentMessages)` returns wire message with populated `attachments: Array<{ type: "image" | "file", url: string, filename: string, size?: number }>`.

- [ ] **Step 1: Write failing unit tests in `bridges/zalo-bridge/test/protocol.test.js`**

Add tests for:
1. Quoted photo resolved via `recentMessages` cache lookup.
2. Quoted photo resolved via `quote.attach` JSON payload when cache miss.
3. Quoted photo resolved via `quote.attach` direct image URL when cache miss.
4. Quoted file resolved via `quote.attach` with `cliMsgType: 46`.
5. Quoted text message does not produce attachments.

```javascript
test("formatInboundMessage extracts quoted photo from recentMessages cache", () => {
  const recentMessages = new Map();
  recentMessages.set("msg_photo_orig", {
    msgId: "msg_photo_orig",
    msgType: "chat.photo",
    content: {
      href: "https://res-zalo.zadn.vn/photo/cached_hd.jpg",
      thumb: "https://res-zalo.zadn.vn/photo/cached_thumb.jpg",
      description: "Original photo caption",
    },
  });

  const replyMsg = {
    type: 1, // group
    threadId: "group_100",
    isSelf: false,
    data: {
      msgId: "msg_reply_1",
      msgType: "webchat",
      uidFrom: "user_user1",
      dName: "Bob",
      content: "@Bot please analyze this picture",
      mentions: [{ uid: "bot_999", pos: 0, len: 4 }],
      quote: {
        globalMsgId: "msg_photo_orig",
        cliMsgId: "msg_photo_orig",
        cliMsgType: 32,
        msg: "Original photo caption",
      },
      ts: "1725390020000",
    },
  };

  const wire = formatInboundMessage(replyMsg, recentMessages);
  assert.equal(wire.content, "@Bot please analyze this picture");
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "image");
  assert.equal(wire.attachments[0].url, "https://res-zalo.zadn.vn/photo/cached_hd.jpg");
  assert.equal(wire.attachments[0].filename, "cached_hd.jpg");
});

test("formatInboundMessage extracts quoted photo from quote.attach JSON payload when cache miss", () => {
  const replyMsg = {
    type: 1,
    threadId: "group_100",
    isSelf: false,
    data: {
      msgId: "msg_reply_2",
      msgType: "webchat",
      uidFrom: "user_user1",
      dName: "Bob",
      content: "@Bot explain this formula",
      quote: {
        globalMsgId: "msg_non_cached",
        cliMsgType: 32,
        attach: JSON.stringify({
          hdUrl: "https://res-zalo.zadn.vn/photo/formula_hd.png",
          thumb: "https://res-zalo.zadn.vn/photo/formula_thumb.png",
        }),
      },
      ts: "1725390030000",
    },
  };

  const wire = formatInboundMessage(replyMsg);
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "image");
  assert.equal(wire.attachments[0].url, "https://res-zalo.zadn.vn/photo/formula_hd.png");
  assert.equal(wire.attachments[0].filename, "formula_hd.png");
});

test("formatInboundMessage extracts quoted photo from quote.attach direct URL when cache miss", () => {
  const replyMsg = {
    type: 1,
    threadId: "group_100",
    isSelf: false,
    data: {
      msgId: "msg_reply_3",
      msgType: "webchat",
      uidFrom: "user_user1",
      dName: "Bob",
      content: "check this",
      quote: {
        globalMsgId: "msg_direct_url",
        cliMsgType: 32,
        attach: "https://res-zalo.zadn.vn/photo/graph.jpg",
      },
      ts: "1725390040000",
    },
  };

  const wire = formatInboundMessage(replyMsg);
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "image");
  assert.equal(wire.attachments[0].url, "https://res-zalo.zadn.vn/photo/graph.jpg");
});

test("formatInboundMessage extracts quoted document from quote.attach with cliMsgType 46", () => {
  const replyMsg = {
    type: 1,
    threadId: "group_100",
    isSelf: false,
    data: {
      msgId: "msg_reply_4",
      msgType: "webchat",
      uidFrom: "user_user1",
      dName: "Bob",
      content: "summarize this file",
      quote: {
        globalMsgId: "msg_doc_1",
        cliMsgType: 46,
        msg: "research_paper.pdf",
        attach: JSON.stringify({
          href: "https://d-zalo.zadn.vn/file/research_paper.pdf",
          fileSize: 204800,
          title: "research_paper.pdf",
        }),
      },
      ts: "1725390050000",
    },
  };

  const wire = formatInboundMessage(replyMsg);
  assert.equal(wire.attachments.length, 1);
  assert.equal(wire.attachments[0].type, "file");
  assert.equal(wire.attachments[0].filename, "research_paper.pdf");
  assert.equal(wire.attachments[0].url, "https://d-zalo.zadn.vn/file/research_paper.pdf");
  assert.equal(wire.attachments[0].size, 204800);
});

test("formatInboundMessage does not produce attachments when quoted message is plain text", () => {
  const replyMsg = {
    type: 1,
    threadId: "group_100",
    isSelf: false,
    data: {
      msgId: "msg_reply_5",
      msgType: "webchat",
      uidFrom: "user_user1",
      dName: "Bob",
      content: "yes I agree",
      quote: {
        globalMsgId: "msg_txt_1",
        cliMsgType: 1,
        msg: "Let's meet at 2pm",
      },
      ts: "1725390060000",
    },
  };

  const wire = formatInboundMessage(replyMsg);
  assert.equal(wire.attachments.length, 0);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test bridges/zalo-bridge/test/protocol.test.js`
Expected: FAIL on the new quoted photo tests because `formatInboundMessage` does not extract attachments from quotes.

- [ ] **Step 3: Implement `extractAttachments` and quote fallback in `bridges/zalo-bridge/src/protocol.js` & `server.js`**

In `bridges/zalo-bridge/src/protocol.js`:
1. Define `extractAttachments(rawContent, msgType = "")`:
```javascript
export function extractAttachments(rawContent, msgType = "") {
  let content = rawContent;
  if (
    typeof content === "string" &&
    content.trim().startsWith("{") &&
    content.trim().endsWith("}")
  ) {
    try {
      content = JSON.parse(content);
    } catch {
      // keep original
    }
  }

  const attachments = [];
  if (!content || typeof content !== "object") {
    return attachments;
  }

  const isPhotoMsg =
    msgType === "chat.photo" ||
    Boolean(
      content.thumb ||
      content.thumbUrl ||
      content.hdUrl ||
      content.oriUrl ||
      content.normalUrl
    );

  if (isPhotoMsg) {
    const imgUrl =
      content.hdUrl ||
      content.oriUrl ||
      content.normalUrl ||
      content.href ||
      content.thumb ||
      content.thumbUrl ||
      content.url;

    if (imgUrl && typeof imgUrl === "string") {
      let filename = "photo.jpg";
      try {
        const parsedPath = new URL(imgUrl).pathname;
        const base = parsedPath.split("/").pop();
        if (base && /\.(jpg|jpeg|png|webp|gif)$/i.test(base)) {
          filename = base;
        }
      } catch {
        // fallback
      }
      attachments.push({
        type: "image",
        url: imgUrl,
        filename,
      });
    }
  } else if (
    msgType === "share.file" ||
    Boolean(content.fileSize || content.size)
  ) {
    const fileUrl = content.href || content.url;
    if (fileUrl && typeof fileUrl === "string") {
      const filename = String(
        content.title || content.fileName || "document"
      );
      const size = Number(content.fileSize || content.size || 0);
      attachments.push({
        type: "file",
        url: fileUrl,
        filename,
        ...(size > 0 ? { size } : {}),
      });
    }
  }

  return attachments;
}
```

2. In `formatInboundMessage(message, recentMessages)`:
- Extract top-level attachments with `extractAttachments(rawContent, msgType)`.
- If `attachments.length === 0 && data.quote`:
  - **Tier 1 (Cache lookup):**
    ```javascript
    const quote = data.quote;
    const quoteId = String(quote.globalMsgId || quote.cliMsgId || quote.msgId || "");
    if (recentMessages && quoteId && recentMessages.has(quoteId)) {
      const cached = recentMessages.get(quoteId);
      const cachedAtts = extractAttachments(cached?.content, cached?.msgType);
      if (cachedAtts.length > 0) {
        attachments.push(...cachedAtts);
      }
    }
    ```
  - **Tier 2 (Quote attach parse):**
    ```javascript
    if (attachments.length === 0 && quote.attach) {
      let attachObj = quote.attach;
      if (typeof attachObj === "string" && attachObj.trim().startsWith("{")) {
        try {
          attachObj = JSON.parse(attachObj);
        } catch {}
      }
      const quoteMsgType =
        quote.cliMsgType === 32
          ? "chat.photo"
          : quote.cliMsgType === 46
          ? "share.file"
          : "";

      if (attachObj && typeof attachObj === "object") {
        const parsedAtts = extractAttachments(attachObj, quoteMsgType);
        if (parsedAtts.length > 0) {
          attachments.push(...parsedAtts);
        }
      } else if (typeof attachObj === "string" && /^https?:\/\//i.test(attachObj)) {
        if (quote.cliMsgType === 32 || /\.(jpg|jpeg|png|webp|gif)$/i.test(attachObj)) {
          let filename = "photo.jpg";
          try {
            const base = new URL(attachObj).pathname.split("/").pop();
            if (base) filename = base;
          } catch {}
          attachments.push({ type: "image", url: attachObj, filename });
        } else if (quote.cliMsgType === 46) {
          attachments.push({
            type: "file",
            url: attachObj,
            filename: String(quote.msg || "document"),
          });
        }
      }
    }
    ```

3. In `bridges/zalo-bridge/src/server.js`:
Pass `this.recentMessages` into `formatInboundMessage`:
```javascript
this.broadcast(formatInboundMessage(msg, this.recentMessages));
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test bridges/zalo-bridge/test/protocol.test.js`
Expected: ALL pass.

- [ ] **Step 5: Commit**

```bash
git add bridges/zalo-bridge/src/protocol.js bridges/zalo-bridge/src/server.js bridges/zalo-bridge/test/protocol.test.js
git commit -m "feat(zalo-bridge): extract media attachments from quoted messages"
```

---

### Task 2: Python Channel Mention Stripping & Quoted Media Processing

**Files:**
- Modify: `deeptutor/partners/channels/zalo.py:365-420`
- Test: `tests/services/partners/test_zalo_channel.py`

**Interfaces:**
- Consumes: Inbound wire message with `attachments` extracted from quote and `mentions`/`content` with `@BotName`.
- Produces: `_handle_message(sender_id, chat_id, content=clean_content, media=media_paths, metadata=metadata)`.

- [ ] **Step 1: Write failing unit tests in `tests/services/partners/test_zalo_channel.py`**

Add tests for:
1. Inbound group message quoting a photo with `@BotName hãy giải bài này`:
   - Bot mention is stripped so `content` becomes `"hãy giải bài này"`.
   - Quoted image attachment is downloaded into `media_paths`.
   - `mock_bus.publish_inbound` receives `media` containing the local image path.
2. Inbound group message quoting a photo with ONLY `@BotName` (no other text):
   - Fallback prompt `"Please analyze the attached image(s)."` is set as `content`.
   - Quoted image attachment is downloaded into `media_paths`.
3. Inbound group message quoting a document file with text `"tóm tắt file"`:
   - Document attachment is downloaded and passed in `media`.

```python
@pytest.mark.asyncio
async def test_zalo_inbound_group_quote_photo_with_text(mock_bus, tmp_path, monkeypatch):
    import httpx
    from unittest.mock import AsyncMock

    async def mock_get(client, url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {"content-length": "100"}
        resp.content = b"fake-jpeg-image-bytes"
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    config = ZaloConfig(
        enabled=True,
        allow_from=["*"],
        group_policy="mention",
        bot_name="MyBot",
        bot_user_id="bot_999",
    )
    channel = ZaloChannel(config, mock_bus)
    channel.media_dir = MagicMock(return_value=tmp_path)

    payload = {
        "type": "message",
        "id": "reply_msg_001",
        "thread_id": "group_999",
        "thread_type": "group",
        "sender_id": "user_123",
        "sender_name": "Bob",
        "content": "@MyBot hãy giải thích bài tập này",
        "is_self": False,
        "mentions": [{"uid": "bot_999", "pos": 0, "len": 6}],
        "quote": {
            "globalMsgId": "photo_msg_000",
            "cliMsgType": 32,
            "msg": "Bai tap toan",
        },
        "attachments": [
            {
                "type": "image",
                "url": "https://res-zalo.zadn.vn/photo/exercise.jpg",
                "filename": "exercise.jpg",
            }
        ],
        "timestamp": 1725390000000,
    }

    await channel._handle_bridge_message(json.dumps(payload))

    mock_bus.publish_inbound.assert_called_once()
    inbound: InboundMessage = mock_bus.publish_inbound.call_args[0][0]
    assert inbound.chat_id == "group:group_999"
    assert inbound.content == "hãy giải thích bài tập này"
    assert len(inbound.media) == 1
    assert inbound.media[0].endswith("exercise.jpg")
    assert Path(inbound.media[0]).exists()


@pytest.mark.asyncio
async def test_zalo_inbound_group_quote_photo_mention_only(mock_bus, tmp_path, monkeypatch):
    import httpx

    async def mock_get(client, url, *args, **kwargs):
        resp = MagicMock(spec=httpx.Response)
        resp.status_code = 200
        resp.headers = {"content-length": "100"}
        resp.content = b"fake-jpeg-image-bytes"
        resp.raise_for_status = MagicMock()
        return resp

    monkeypatch.setattr(httpx.AsyncClient, "get", mock_get)

    config = ZaloConfig(
        enabled=True,
        allow_from=["*"],
        group_policy="mention",
        bot_name="MyBot",
        bot_user_id="bot_999",
    )
    channel = ZaloChannel(config, mock_bus)
    channel.media_dir = MagicMock(return_value=tmp_path)

    payload = {
        "type": "message",
        "id": "reply_msg_002",
        "thread_id": "group_999",
        "thread_type": "group",
        "sender_id": "user_123",
        "content": "@MyBot",
        "is_self": False,
        "mentions": [{"uid": "bot_999", "pos": 0, "len": 6}],
        "quote": {"globalMsgId": "photo_msg_000", "cliMsgType": 32},
        "attachments": [
            {
                "type": "image",
                "url": "https://res-zalo.zadn.vn/photo/exercise.jpg",
                "filename": "exercise.jpg",
            }
        ],
        "timestamp": 1725390000000,
    }

    await channel._handle_bridge_message(json.dumps(payload))

    mock_bus.publish_inbound.assert_called_once()
    inbound: InboundMessage = mock_bus.publish_inbound.call_args[0][0]
    assert inbound.content == "Please analyze the attached image(s)."
    assert len(inbound.media) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest tests/services/partners/test_zalo_channel.py -k "quote_photo" -v`
Expected: FAIL because bot mention stripping is not implemented yet (`inbound.content` still has `@MyBot ...`).

- [ ] **Step 3: Update `deeptutor/partners/channels/zalo.py`**

In `_handle_bridge_message()`:
1. Clean mention text:
```python
            # Clean bot mentions from content if in group
            clean_content = content
            bot_name = str(self.config.bot_name or self._bot_display_name or "").strip()
            if bot_name:
                import re
                clean_content = re.sub(rf"@{re.escape(bot_name)}\b", "", clean_content, flags=re.IGNORECASE).strip()

            attachments = data.get("attachments") or []
            media_paths: list[str] = []
            if attachments:
                media_paths = await self._download_attachments(attachments)

            if not clean_content and attachments:
                if all(att.get("type") == "image" for att in attachments):
                    clean_content = "Please analyze the attached image(s)."
                else:
                    clean_content = "Please use the attached file(s)."
            elif not clean_content:
                clean_content = content
```
2. Pass `clean_content` to `_handle_message(..., content=clean_content, media=media_paths, ...)`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/services/partners/test_zalo_channel.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add deeptutor/partners/channels/zalo.py tests/services/partners/test_zalo_channel.py
git commit -m "feat(zalo): clean bot mentions and process quoted media attachments"
```

---

### Task 3: End-to-End Verification & Regressions Check

**Files:**
- Test: `bridges/zalo-bridge/test/protocol.test.js`
- Test: `tests/partners/test_zalo_formatter.py`
- Test: `tests/services/partners/test_zalo_channel.py`

- [ ] **Step 1: Run all Node.js bridge tests**

Run: `node --test bridges/zalo-bridge/test/*.test.js`
Expected: All tests pass.

- [ ] **Step 2: Run all Python Zalo tests**

Run: `.venv/bin/pytest tests/partners/test_zalo_formatter.py tests/services/partners/test_zalo_channel.py -v`
Expected: All tests pass.

- [ ] **Step 3: Verify git status is clean**

Run: `git status`
Expected: Clean working tree on branch `feat/vn-support`.
