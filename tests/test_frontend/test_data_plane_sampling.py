import pytest
import json
from unittest.mock import MagicMock, AsyncMock
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_sampling_reverse_routing():
    """バックエンドからのリクエストIDを記録し、AIのレスポンスを正しく送り返すかを網羅"""
    mock_client = MagicMock()
    mock_client.forward_request = AsyncMock()
    
    server = DataPlaneServer(registry=MagicMock(), backend_client=mock_client)
    
    # 1. バックエンドからLLMへの要求を受信したと想定し、IDを記録させる
    backend_req = json.dumps({"jsonrpc": "2.0", "id": "sample-123", "method": "sampling/createMessage"})
    server._handle_backend_message(backend_req, "/mcp/serverA")
    assert server._response_routes["sample-123"] == "/mcp/serverA"
    
    # 2. AIからの応答を処理させる
    ai_response = json.dumps({"jsonrpc": "2.0", "id": "sample-123", "result": {"content": "Hello"}})
    await server._handle_message(ai_response)
    
    # 3. 正しいバックエンドに転送されたか検証
    mock_client.forward_request.assert_called_once()
    called_route, payload = mock_client.forward_request.call_args[0]
    assert called_route == "/mcp/serverA"
    assert payload["result"]["content"] == "Hello"
    
    # 4. 未知のIDへの応答が来た場合のWarningパス
    ai_unknown = json.dumps({"jsonrpc": "2.0", "id": "unknown-999", "result": {"content": "Who?"}})
    await server._handle_message(ai_unknown)
    assert mock_client.forward_request.call_count == 1 # 呼び出し回数が増えていないことを確認