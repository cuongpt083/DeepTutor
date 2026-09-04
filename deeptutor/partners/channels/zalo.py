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
