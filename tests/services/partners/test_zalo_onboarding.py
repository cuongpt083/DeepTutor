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


def test_channel_onboarding_start_request_allows_zalo():
    from deeptutor.api.routers.partners import ChannelOnboardingStartRequest

    req = ChannelOnboardingStartRequest(channel="zalo")
    assert req.channel == "zalo"


@pytest.mark.asyncio
async def test_request_zalo_qr_handles_buffered_frames():
    import json

    manager = ChannelOnboardingManager()

    class FakeWebSocket:
        def __init__(self, responses):
            self._responses = list(responses)
            self.sent = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def send(self, data):
            self.sent.append(json.loads(data))

        async def recv(self):
            if not self._responses:
                raise TimeoutError("No more frames")
            return self._responses.pop(0)

    # Simulate: auth_ok -> status -> qr_generated
    fake_frames = [
        json.dumps({"type": "auth_ok"}),
        json.dumps({"type": "status", "status": "ready_for_login"}),
        json.dumps({
            "type": "qr_generated",
            "data": {"qr_data_url": "data:image/png;base64,abc", "token": "tok123"},
        }),
    ]

    with patch("websockets.connect", return_value=FakeWebSocket(fake_frames)):
        qr_data = await manager._request_zalo_qr("ws://127.0.0.1:3002", "test-token")
        assert qr_data["qr_data_url"] == "data:image/png;base64,abc"
        assert qr_data["token"] == "tok123"


@pytest.mark.asyncio
async def test_poll_zalo_connected():
    import json
    from datetime import datetime, timezone
    from deeptutor.services.partners.channel_onboarding import OnboardingSession

    manager = ChannelOnboardingManager()
    session = OnboardingSession(
        session_id="s1",
        partner_id="nutritech",
        channel="zalo",
        status="pending_scan",
        qr_payload="mock",
        fallback_url="",
        poll_interval_seconds=3,
        deadline_monotonic=1000.0,
        expires_at=datetime.now(timezone.utc),
        zalo_bridge_url="ws://127.0.0.1:3002",
        zalo_token="test-token",
    )

    class FakeWebSocket:
        def __init__(self, responses):
            self._responses = list(responses)
            self.sent = []

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

        async def send(self, data):
            self.sent.append(json.loads(data))

        async def recv(self):
            if not self._responses:
                raise TimeoutError("No more frames")
            return self._responses.pop(0)

    fake_frames = [
        json.dumps({"type": "auth_ok"}),
        json.dumps({"type": "status", "status": "connected", "user_id": "zalo-uid-456"}),
    ]

    with patch("websockets.connect", return_value=FakeWebSocket(fake_frames)):
        await manager._poll_zalo(session)
        assert session.status == "ready"
        assert session.credentials.get("user_id") == "zalo-uid-456"


@pytest.mark.asyncio
async def test_zalo_raw_base64_qr_payload():
    manager = ChannelOnboardingManager()
    raw_base64 = "iVBORw0KGgoAAAANSUhEUgAAAY8AAAGPCAYAAACkmlzn"
    mock_qr_payload = {
        "qr_data_url": raw_base64,
        "code": "https://qr.zalo.me/pc/login?code=123",
        "token": "tok123",
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
        result = await manager.start("test-partner", "zalo")
        assert result["qr_data_url"].startswith("data:image/png;base64,iVBORw0KGgo")
        assert result["fallback_url"] == "https://qr.zalo.me/pc/login?code=123"


