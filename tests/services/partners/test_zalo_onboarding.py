"""Tests for Zalo QR onboarding integration."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
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

    mock_partner_config = MagicMock()
    mock_partner_config.channels = {"zalo": {"bridge_url": "ws://127.0.0.1:3002"}}
    mock_partner_manager = MagicMock()
    mock_partner_manager.load_config.return_value = mock_partner_config
    mock_partner_manager.get_partner.return_value = None

    with (
        patch(
            "deeptutor.services.partners.manager.get_partner_manager",
            return_value=mock_partner_manager,
        ),
        patch.object(
            manager, "_request_zalo_qr", new=AsyncMock(return_value=mock_qr_payload)
        ),
    ):
        start_result = await manager.start("test-partner", "zalo")
        assert start_result["channel"] == "zalo"
        assert start_result["status"] == "pending_scan"
        assert start_result["qr_data_url"] == "data:image/png;base64,mockqrdata"
        session_id = start_result["session_id"]
        assert session_id is not None

        # Simulate mobile scan
        session = manager._sessions[session_id]
        session.status = "scanned"
        status_res = await manager.status("test-partner", session_id)
        assert status_res["status"] == "scanned"

        # Simulate ready
        session.status = "ready"
        session.credentials = {"connected": "true"}
        applied = await manager.apply("test-partner", session_id, mock_partner_manager)
        assert applied["session"]["status"] == "applied"
        assert applied["channels"]["zalo"]["enabled"] is True
