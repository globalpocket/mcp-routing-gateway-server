import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_fetch_tools_boundary_conditions():
    client = BackendClient()
    
    # 1. endpointイベントが一件も来ないまま終了するパス
    async def mock_aiter_empty():
        if False: yield None
    
    mock_event_source = MagicMock()
    mock_event_source.aiter_sse.return_value = mock_aiter_empty()
    
    with patch("httpx_sse.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_event_source))):
        tools = await client.fetch_tools("/none")
        assert tools == []

    # 2. forward_request 中の例外パス
    with patch.object(client, "ensure_connected", side_effect=Exception("Wait error")):
        mock_stdout = MagicMock()
        client.stdout_callback = mock_stdout
        await client.forward_request("/r", {"id": "err"})
        assert "Gateway Forwarding Error" in mock_stdout.call_args[0][0]