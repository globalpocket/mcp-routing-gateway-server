import pytest
import json
import time
from unittest.mock import MagicMock, AsyncMock, patch
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_sampling_reverse_routing(capsys):
    """バックエンドからのリクエストIDを記録し、AIのレスポンスを正しく送り返すかを網羅"""
    mock_client = MagicMock()
    mock_client.forward_request = AsyncMock()
    
    server = DataPlaneServer(registry=MagicMock(), backend_client=mock_client)
    
    # 1. バックエンドからLLMへの要求を受信 (ID: 123)
    backend_req = json.dumps({"jsonrpc": "2.0", "id": 123, "method": "sampling/createMessage"})
    server._handle_backend_message(backend_req, "/mcp/serverA")
    
    # GatewayがAIに流す前に、IDを独自のもの（/mcp/serverA::123）にすり替えているか確認
    captured = capsys.readouterr()
    assert '"id": "/mcp/serverA::123"' in captured.out
    
    # 辞書にも独自のIDで保存されていること
    assert "/mcp/serverA::123" in server._response_routes
    assert server._response_routes["/mcp/serverA::123"]["route"] == "/mcp/serverA"
    assert server._response_routes["/mcp/serverA::123"]["original_id"] == 123
    
    # 2. AIからの応答を処理させる (AIはすり替えられたIDで返してくる)
    ai_response = json.dumps({"jsonrpc": "2.0", "id": "/mcp/serverA::123", "result": {"content": "Hello"}})
    await server._handle_message(ai_response)
    
    # 3. 正しいバックエンドに、元のID（123）に書き戻されて転送されたか検証
    mock_client.forward_request.assert_called_once()
    called_route, payload = mock_client.forward_request.call_args[0]
    assert called_route == "/mcp/serverA"
    assert payload["id"] == 123  # <--- 重要: 123に復元されていること
    assert payload["result"]["content"] == "Hello"
    
    # 4. 未知のIDへの応答が来た場合のWarningパス
    ai_unknown = json.dumps({"jsonrpc": "2.0", "id": "unknown-999", "result": {"content": "Who?"}})
    await server._handle_message(ai_unknown)
    assert mock_client.forward_request.call_count == 1 # 呼び出し回数が増えていないことを確認

def test_sampling_memory_leak_protection():
    """メモリリーク対策（タイムアウトと上限サイズ）が機能するか検証"""
    server = DataPlaneServer(registry=MagicMock())
    
    # 意図的に上限サイズを小さくしてテスト
    server.MAX_ROUTES = 2
    server.ROUTE_TIMEOUT = 10
    
    # 1. 上限サイズの検証 (LRU方式)
    server._handle_backend_message(json.dumps({"jsonrpc": "2.0", "id": "id1", "method": "m"}), "/r1")
    server._handle_backend_message(json.dumps({"jsonrpc": "2.0", "id": "id2", "method": "m"}), "/r2")
    server._handle_backend_message(json.dumps({"jsonrpc": "2.0", "id": "id3", "method": "m"}), "/r3")
    
    # すり替え後のIDで保存されている
    key1 = "/r1::id1"
    key2 = "/r2::id2"
    key3 = "/r3::id3"
    
    # 上限2なので、最初の key1 が消えて key2, key3 だけが残るはず
    assert key1 not in server._response_routes
    assert key2 in server._response_routes
    assert key3 in server._response_routes
    
    # 2. タイムアウトの検証
    # time.time() をモックして時間を進める
    with patch("time.time", return_value=time.time() + 20):
        # 新しいメッセージが来たタイミングでクリーンアップが走る
        server._handle_backend_message(json.dumps({"jsonrpc": "2.0", "id": "id4", "method": "m"}), "/r4")
        key4 = "/r4::id4"
        
        # 以前の key2, key3 はタイムアウトで消え、key4 だけが残る
        assert key2 not in server._response_routes
        assert key3 not in server._response_routes
        assert key4 in server._response_routes