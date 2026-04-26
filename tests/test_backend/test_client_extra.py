import pytest
import asyncio
from unittest.mock import patch
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