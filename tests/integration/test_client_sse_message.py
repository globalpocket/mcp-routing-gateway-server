import pytest
import asyncio
from unittest.mock import MagicMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_client_receives_sse_message():
    """製品(client.py)を一切修正せず、正しい手順でメッセージ受信を検証する"""
    mock_callback = MagicMock()
    # ターミナル1の mock_backend.py(8765番) に接続
    client = BackendClient(base_url="http://127.0.0.1:8765", stdout_callback=mock_callback)
    
    # _stream_task を直接 create_task せず、ensure_connected を呼ぶ
    await client.ensure_connected("/mcp/server_mock")
    
    # スタブへリクエストを転送し、スタブからの message 受信を誘発
    await client.forward_request("/mcp/server_mock", {
        "jsonrpc": "2.0", "id": "sse-test-1", "method": "tools/call", 
        "params": {"name": "read_file", "arguments": {}}
    })
    
    # 巡回待機
    await asyncio.sleep(1.0)
    
    # 検証
    assert mock_callback.called
    
    # 後処理
    if "/mcp/server_mock" in client._streams:
        client._streams["/mcp/server_mock"]["task"].cancel()