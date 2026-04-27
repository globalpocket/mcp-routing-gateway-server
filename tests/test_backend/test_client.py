import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_forward_request_is_fire_and_forget():
    """
    forward_request がレスポンスを待たずに(ブロッキングせずに)
    POSTリクエストをバックグラウンドタスクとして発火させているかを検証
    """
    # モック用の stdout コールバック
    mock_stdout = MagicMock()
    client = BackendClient(stdout_callback=mock_stdout)
    
    # SSEの接続待機をモック化（すぐにダミーURLを返すようにする）
    client.ensure_connected = AsyncMock(return_value="http://localhost:8000/mcp/serverA/message")
    
    # httpx.AsyncClient の post メソッドをモック化 (Warning解消のため、raise_for_statusを持つ通常のMockを返す)
    mock_res = MagicMock()
    mock_res.raise_for_status = MagicMock()
    client.client.post = AsyncMock(return_value=mock_res)
    
    # 転送するダミーのリクエスト
    req_payload = {"jsonrpc": "2.0", "id": "test-id-1", "method": "tools/call", "params": {"name": "read_file"}}
    
    # 実行
    await client.forward_request("/mcp/serverA", req_payload)
    
    # POST処理は非同期(create_task)で発火するため、イベントループを少し回す
    await asyncio.sleep(0.01)
    
    # 検証1: ensure_connected が正しいルートで呼ばれたか
    client.ensure_connected.assert_called_once_with("/mcp/serverA")
    
    # 検証2: client.post が、変更されていないペイロード(req_payload)で実行されたか
    client.client.post.assert_called_once_with(
        "http://localhost:8000/mcp/serverA/message", 
        json=req_payload
    )
    
    # 検証3: Gateway自身が勝手に標準出力(stdout)へ書き込みをしていないか
    # (レスポンスは後からSSEで降ってきたものを _stream_task が書き込むべき)
    mock_stdout.assert_not_called()