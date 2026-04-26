import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_fetch_tools_error_branches():
    client = BackendClient()
    
    # 1. endpoint が見つからないケース
    async def mock_aiter_no_endpoint():
        yield MagicMock(event="other", data="data")
    
    mock_source = MagicMock()
    mock_source.aiter_sse.return_value = mock_aiter_no_endpoint()
    
    with patch("httpx_sse.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        assert await client.fetch_tools("/none") == []

    # 2. fetch中に例外が発生するケース (except Exception網羅)
    with patch("httpx.AsyncClient.get", side_effect=Exception("SSE Fail")):
        assert await client.fetch_tools("/err") == []

    # 3. messageイベントが来たが、IDが一致しないケース
    async def mock_aiter_wrong_id():
        yield MagicMock(event="endpoint", data="/post")
        yield MagicMock(event="message", data=json.dumps({"id": "wrong", "result": {}}))
    
    mock_source.aiter_sse.return_value = mock_aiter_wrong_id()
    with patch("httpx_sse.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        with patch("httpx.AsyncClient.post", return_value=AsyncMock()):
            # タイムアウトまで待機させて Miss 行を踏ませる
            assert await client.fetch_tools("/wrong") == []