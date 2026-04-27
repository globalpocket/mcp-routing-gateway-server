import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_fetch_tools_success():
    """初期化ハンドシェイクを含む正常系のツール取得を網羅"""
    client = BackendClient()
    async def mock_aiter_success():
        yield MagicMock(event="endpoint", data="/post")
        # initialize response
        yield MagicMock(event="message", data=json.dumps({"id": "internal-init", "result": {}}))
        # tools/list response
        yield MagicMock(event="message", data=json.dumps({"id": "internal-fetch", "result": {"tools": [{"name": "test_tool"}]}}))

    mock_source = MagicMock()
    mock_source.aiter_sse.return_value = mock_aiter_success()

    # モックのターゲットをローカル名前空間 (mcp_gateway.backend.client) に正確に指定
    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        with patch("httpx.AsyncClient.post", return_value=AsyncMock()) as mock_post:
            tools = await client.fetch_tools("/success")
            assert tools == [{"name": "test_tool"}]
            # initialize, notifications/initialized, tools/list の計3回 POST が呼ばれることを確認
            assert mock_post.call_count == 3

@pytest.mark.anyio
async def test_fetch_tools_error_branches():
    client = BackendClient()
    
    # 1. endpoint が見つからないケース
    async def mock_aiter_no_endpoint():
        yield MagicMock(event="other", data="data")
    
    mock_source = MagicMock()
    mock_source.aiter_sse.return_value = mock_aiter_no_endpoint()
    
    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        assert await client.fetch_tools("/none") == []

    # 2. fetch中に例外が発生するケース (except Exception網羅)
    with patch("httpx.AsyncClient.get", side_effect=Exception("SSE Fail")):
        assert await client.fetch_tools("/err") == []

    # 3. messageイベントが来たが、IDが一致しないケース (ハンドシェイク失敗)
    async def mock_aiter_wrong_id():
        yield MagicMock(event="endpoint", data="/post")
        yield MagicMock(event="message", data=json.dumps({"id": "wrong", "result": {}}))
    
    mock_source.aiter_sse.return_value = mock_aiter_wrong_id()
    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        with patch("httpx.AsyncClient.post", return_value=AsyncMock()):
            # タイムアウトまで待機させて Miss 行を踏ませる
            assert await client.fetch_tools("/wrong") == []