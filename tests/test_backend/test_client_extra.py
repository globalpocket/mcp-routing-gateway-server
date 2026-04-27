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
        # ハンドシェイク応答 (これがないと ready にならず、次のメッセージを処理しない)
        init_id = "stream-init-/mcp/sanitize"
        yield MagicMock(event="message", data=json.dumps({"jsonrpc": "2.0", "id": init_id, "result": {}}))
        
        # 1. 不正なJSON
        yield MagicMock(event="message", data="invalid{json")
        # 2. jsonrpc 欠損
        yield MagicMock(event="message", data=json.dumps({"id": "1", "result": "ok"}))
        # 3. 正しいJSON-RPC
        yield MagicMock(event="message", data=json.dumps({"jsonrpc": "2.0", "id": "2", "result": "ok"}))

    mock_event_source = MagicMock()
    mock_event_source.aiter_sse.return_value = mock_aiter()

    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_event_source))):
        with patch("httpx.AsyncClient.post", return_value=AsyncMock()):
            task = asyncio.create_task(client._stream_task("/mcp/sanitize"))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    assert mock_callback.call_count == 1
    assert "2.0" in mock_callback.call_args[0][0]
    assert "Invalid message format" in caplog.text

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

@pytest.mark.anyio
async def test_client_forward_post_error(caplog):
    """バックエンドへのPOST転送時にエラー(500等)が出た際、LLMにエラーを返すかを検証"""
    client = BackendClient()
    mock_callback = MagicMock()
    client.message_callback = mock_callback
    
    req = {"jsonrpc": "2.0", "id": "req-99", "method": "tools/call"}
    
    with patch.object(client.client, "post", side_effect=Exception("HTTP 500")):
        await client._do_post("http://test", req, "/mcp/test")
        
    assert mock_callback.call_count == 1
    assert "Gateway Forwarding Error: HTTP 500" in mock_callback.call_args[0][0]

@pytest.mark.anyio
async def test_stream_task_handshake():
    """永続ストリーム接続時の initialize ハンドシェイクを検証"""
    client = BackendClient()
    init_id = "stream-init-/mcp/handshake"
    
    async def mock_aiter_init():
        yield MagicMock(event="endpoint", data="/post")
        # initialize 応答を模倣
        yield MagicMock(event="message", data=json.dumps({"jsonrpc": "2.0", "id": init_id, "result": {}}))
        # 無限待機
        while True: await asyncio.sleep(0.1)

    mock_source = MagicMock()
    mock_source.aiter_sse.return_value = mock_aiter_init()

    with patch("mcp_gateway.backend.client.aconnect_sse", return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_source))):
        with patch("httpx.AsyncClient.post", return_value=AsyncMock()) as mock_post:
            # タスクを起動
            task = asyncio.create_task(client._stream_task("/mcp/handshake"))
            
            # ready イベントがセットされるまで待機 (最大1秒)
            try:
                await asyncio.wait_for(client.ensure_connected("/mcp/handshake"), timeout=1.0)
            finally:
                task.cancel()
            
            # initialize と notifications/initialized の2回 POST が呼ばれていることを確認
            # (1回目はendpoint受信直後、2回目はinit結果受信後)
            assert mock_post.call_count >= 2
            assert init_id in str(mock_post.call_args_list[0])