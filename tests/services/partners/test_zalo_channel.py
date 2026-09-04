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
