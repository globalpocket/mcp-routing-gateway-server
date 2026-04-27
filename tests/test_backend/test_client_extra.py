import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_client_reconnect_on_failure():
    """SSE接続が失敗した際に例外をキャッチし、再接続を試みるロジックを網羅"""
    client = BackendClient(base_url="http://invalid-url")
    
    # 接続失敗をシミュレートし、内部のExceptionブロックを通す
    with patch("httpx_sse.aconnect_sse", side_effect=Exception("Connection Failed")):
        # 非同期タスクとして再接続ループを起動
        task = asyncio.create_task(client._stream_task("/mcp/target"))
        
        # ループ内の Exception 処理と asyncio.sleep(3) の開始を待機
        await asyncio.sleep(0.1) 
        
        # タスクをキャンセルすることで、ループを安全に脱出させる
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

@pytest.mark.anyio
async def test_client_sanitize_invalid_json(caplog):
    """バックエンドからの不正なSSEメッセージ(JSON破損、jsonrpc欠損)をサニタイズするか検証"""
    client = BackendClient()
    mock_callback = MagicMock()
    client.message_callback = mock_callback

    async def mock_aiter():
        yield MagicMock(event="endpoint", data="/post")
        # 1. 不正なJSON (stdioに流れてはいけない)
        yield MagicMock(event="message", data="invalid{json")
        # 2. jsonrpc フィールドがないJSON (stdioに流れてはいけない)
        yield MagicMock(event="message", data=json.dumps({"id": "1", "result": "ok"}))
        # 3. 正しいJSON-RPC (stdioに流れるべき)
        yield MagicMock(event="message", data=json.dumps({"jsonrpc": "2.0", "id": "2", "result": "ok"}))

    mock_event_source = MagicMock()
    mock_event_source.aiter_sse.return_value = mock_aiter()

    # パッチのターゲットを正確に指定
    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_event_source))):
        # ループを回すためのタスクを立てて少し待機し、すぐにキャンセルする
        task = asyncio.create_task(client._stream_task("/mcp/sanitize"))
        await asyncio.sleep(0.2) # 反映待ち時間を少し延長
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    # 検証1: 正しいJSON-RPCの1件だけがコールバック(stdio出力)に渡されていること
    assert mock_callback.call_count == 1
    assert "2.0" in mock_callback.call_args[0][0]

    # 検証2: 不正なデータはエラーログとして詳細に記録されていること（握りつぶされていない）
    assert "Invalid message format" in caplog.text
    assert "invalid{json" in caplog.text
    assert "Missing or invalid 'jsonrpc'" in caplog.text

@pytest.mark.anyio
async def test_client_disconnect():
    """disconnect メソッドがタスクを正しくキャンセルし、リソースを解放することを検証"""
    client = BackendClient()
    mock_task = MagicMock()
    mock_task.done.return_value = False
    
    client._streams["/mcp/test"] = {"task": mock_task}
    
    client.disconnect("/mcp/test")
    
    mock_task.cancel.assert_called_once()
    assert "/mcp/test" not in client._streams