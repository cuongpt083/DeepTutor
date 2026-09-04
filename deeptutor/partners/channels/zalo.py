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
from deeptutor.partners.channels.zalo_formatter import format_for_zalo
from deeptutor.partners.config.schema import DeliveryOverrides
from deeptutor.partners.helpers import split_message


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
        self._typing_tasks: dict[str, asyncio.Task] = {}

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
        for task in list(self._typing_tasks.values()):
            task.cancel()
        self._typing_tasks.clear()
        if self._ws:
            await self._ws.close()
            self._ws = None

    def _start_typing(self, chat_id: str, thread_type: str = "user") -> None:
        """Start sending periodic typing indicator for a chat."""
        self._stop_typing(chat_id)
        self._typing_tasks[chat_id] = asyncio.create_task(
            self._typing_loop(chat_id, thread_type)
        )

    def _stop_typing(self, chat_id: str) -> None:
        """Stop the typing indicator for a chat."""
        task = self._typing_tasks.pop(chat_id, None)
        if task and not task.done():
            task.cancel()

    async def _typing_loop(self, chat_id: str, thread_type: str) -> None:
        """Periodically send typing indicator to Zalo until stopped or timed out."""
        elapsed = 0.0
        try:
            while elapsed < 120.0:
                if self._ws and self._connected:
                    payload = {
                        "type": "typing",
                        "thread_id": chat_id,
                        "thread_type": thread_type,
                    }
                    await self._ws.send(json.dumps(payload, ensure_ascii=False))
                await asyncio.sleep(4.0)
                elapsed += 4.0
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.debug("Zalo typing loop stopped for {}: {}", chat_id, e)

    async def send(self, msg: OutboundMessage) -> None:
        """Deliver an outbound response message through the Zalo bridge."""
        self._stop_typing(msg.chat_id)

        if not self._ws or not self._connected:
            raise RuntimeError("Zalo bridge is not connected")

        metadata = msg.metadata or {}
        thread_type = metadata.get("thread_type", "user")
        quote_id = metadata.get("origin_message_id") if self.config.reply_with_quote else None

        raw_content = msg.content or ""
        chunks = (
            split_message(raw_content, max_len=1800)
            if len(raw_content) > 1800
            else [raw_content]
        )

        for idx, chunk in enumerate(chunks):
            text, styles = format_for_zalo(chunk)
            payload: dict[str, Any] = {
                "type": "send",
                "thread_id": msg.chat_id,
                "thread_type": thread_type,
                "text": text,
            }
            if styles:
                payload["styles"] = styles
            if idx == 0 and quote_id:
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

            self._start_typing(thread_id, thread_type)

            await self._handle_message(
                sender_id=sender_id,
                chat_id=thread_id,
                content=content,
                metadata=metadata,
            )
