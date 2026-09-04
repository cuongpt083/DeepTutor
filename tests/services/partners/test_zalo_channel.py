"""Tests for Zalo channel configuration and discovery."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from deeptutor.partners.bus.events import InboundMessage, OutboundMessage
from deeptutor.partners.bus.queue import MessageBus
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


@pytest.mark.asyncio
async def test_zalo_typing_indicator_lifecycle(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)
    mock_ws = AsyncMock()
    channel._ws = mock_ws
    channel._connected = True

    # 1. Inbound message triggers typing
    msg_payload = {
        "type": "message",
        "id": "msg-101",
        "thread_id": "user-999",
        "thread_type": "user",
        "sender_id": "user-999",
        "content": "Need help",
    }
    await channel._handle_bridge_message(json.dumps(msg_payload))

    assert "user-999" in channel._typing_tasks
    typing_task = channel._typing_tasks["user-999"]
    assert not typing_task.done()

    # Wait briefly for typing message to be sent via mock_ws
    import asyncio
    await asyncio.sleep(0.05)
    assert mock_ws.send.called
    first_sent = json.loads(mock_ws.send.call_args[0][0])
    assert first_sent["type"] == "typing"
    assert first_sent["thread_id"] == "user-999"

    # 2. Outbound message stops typing
    outbound = OutboundMessage(
        channel="zalo",
        chat_id="user-999",
        content="Here is your answer",
    )
    await channel.send(outbound)
    assert "user-999" not in channel._typing_tasks
    await asyncio.sleep(0)
    assert typing_task.cancelled() or typing_task.done()


@pytest.mark.asyncio
async def test_zalo_outbound_markdown_formatting(mock_bus):
    config = ZaloConfig(enabled=True, allow_from=["*"])
    channel = ZaloChannel(config, mock_bus)
    mock_ws = AsyncMock()
    channel._ws = mock_ws
    channel._connected = True

    outbound = OutboundMessage(
        channel="zalo",
        chat_id="user-123",
        content="# Tiêu đề chính\nThông tin **quan trọng**.",
    )
    await channel.send(outbound)

    mock_ws.send.assert_called_once()
    payload = json.loads(mock_ws.send.call_args[0][0])
    assert payload["type"] == "send"
    assert "📌 Tiêu đề chính" in payload["text"]
    assert "Thông tin quan trọng." in payload["text"]
    assert "**" not in payload["text"]
    assert "#" not in payload["text"]
    assert "styles" in payload
    assert len(payload["styles"]) >= 2
