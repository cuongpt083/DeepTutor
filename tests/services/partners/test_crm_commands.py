import pytest
from unittest.mock import AsyncMock, MagicMock

from deeptutor.services.partners.commands import PartnerCommandHandler, PartnerCommandResult
from deeptutor.partners.bus.events import InboundMessage


@pytest.fixture
def handler():
    store = MagicMock()
    return PartnerCommandHandler(
        partner_id="test_partner",
        config=MagicMock(),
        store=store,
    )


@pytest.mark.asyncio
async def test_pair_success(handler, monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.ensure_started = AsyncMock()
    mock_mgr._connections = {}
    mock_mgr.call_tool = AsyncMock(
        return_value='{"success": true, "coachName": "Nguyễn Văn A"}'
    )

    # Server connection with adapter
    mock_adapter = MagicMock()
    mock_adapter._original_name = "channel_pair"
    mock_conn = MagicMock()
    mock_conn.owner = "shared"
    mock_conn.name = "nutritech-crm"
    mock_conn.adapters = [mock_adapter]
    mock_mgr._connections = {("shared", "nutritech-crm"): mock_conn}

    monkeypatch.setattr(
        "deeptutor.services.mcp.get_mcp_manager", lambda: mock_mgr
    )

    msg = InboundMessage(
        channel="telegram",
        chat_id="chat_123",
        sender_id="123456",
        content="/pair ABCD2345",
    )

    res = await handler.dispatch(msg)
    assert isinstance(res, PartnerCommandResult)
    assert "Ghép nối tài khoản thành công! HLV Nguyễn Văn A" in res.content


@pytest.mark.asyncio
async def test_pair_friendly_error_on_mcp_failure(handler, monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.ensure_started = AsyncMock()
    mock_adapter = MagicMock()
    mock_adapter._original_name = "channel_pair"
    mock_conn = MagicMock()
    mock_conn.owner = "shared"
    mock_conn.name = "nutritech-crm"
    mock_conn.adapters = [mock_adapter]
    mock_mgr._connections = {("shared", "nutritech-crm"): mock_conn}
    mock_mgr.call_tool = AsyncMock(
        return_value="(MCP server 'nutritech-crm' reconnect failed: Connection refused)"
    )

    monkeypatch.setattr(
        "deeptutor.services.mcp.get_mcp_manager", lambda: mock_mgr
    )

    msg = InboundMessage(
        channel="telegram",
        chat_id="chat_123",
        sender_id="123456",
        content="/pair ABCD2345",
    )

    res = await handler.dispatch(msg)
    assert isinstance(res, PartnerCommandResult)
    assert "ClosedResourceError" not in res.content
    assert "Không thể kết nối tới máy chủ CRM" in res.content


@pytest.mark.asyncio
async def test_call_crm_tool_friendly_error_on_mcp_failure(handler, monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.ensure_started = AsyncMock()
    mock_adapter = MagicMock()
    mock_adapter._original_name = "customer_list"
    mock_conn = MagicMock()
    mock_conn.owner = "shared"
    mock_conn.name = "nutritech-crm"
    mock_conn.adapters = [mock_adapter]
    mock_mgr._connections = {("shared", "nutritech-crm"): mock_conn}
    mock_mgr.call_tool = AsyncMock(
        return_value="(MCP tool call failed: ClosedResourceError: )"
    )

    monkeypatch.setattr(
        "deeptutor.services.mcp.get_mcp_manager", lambda: mock_mgr
    )

    msg = InboundMessage(
        channel="telegram",
        chat_id="chat_123",
        sender_id="123456",
        content="/customers",
    )

    from deeptutor_crm_plugin.commands import NutriTechCRMHandler

    crm_handler = NutriTechCRMHandler()
    ok, res = await crm_handler._call_crm_tool(msg, "customer_list")
    assert ok is False
    assert "ClosedResourceError" not in res
    assert "Không thể kết nối tới máy chủ CRM" in res


@pytest.mark.asyncio
async def test_resolve_crm_server_fallback(handler, monkeypatch):
    mock_mgr = MagicMock()
    mock_mgr.ensure_started = AsyncMock()
    mock_conn = MagicMock()
    mock_conn.owner = "shared"
    mock_conn.name = "nutritech-crm"
    mock_conn.adapters = []  # empty adapters
    mock_mgr._connections = {("shared", "nutritech-crm"): mock_conn}
    mock_mgr.call_tool = AsyncMock(
        return_value='{"success": true, "coachName": "Coach"}'
    )

    monkeypatch.setattr(
        "deeptutor.services.mcp.get_mcp_manager", lambda: mock_mgr
    )

    msg = InboundMessage(
        channel="telegram",
        chat_id="chat_123",
        sender_id="123456",
        content="/pair ABCD2345",
    )

    res = await handler.dispatch(msg)
    assert isinstance(res, PartnerCommandResult)
    assert "Ghép nối tài khoản thành công! HLV Coach" in res.content
