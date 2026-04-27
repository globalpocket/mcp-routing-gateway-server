import pytest
import json
from unittest.mock import AsyncMock, MagicMock
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_forward_to_backend_preserves_payload():
    """
    Data Planeがリクエストをバックエンドに転送する際、
    IDや引数(arguments)を一切破壊せず、nameだけを書き換えて横流し(バイパス)することを検証する。
    """
    # 1. Mock Registry の準備
    mock_registry = MagicMock()
    # "serverA_read_file" という呼び出しは "/mcp/serverA" の "read_file" に変換される設定
    mock_registry.get_tool_routing_info.return_value = {
        "target_route": "/mcp/serverA",
        "backend_tool_name": "read_file"
    }

    # 2. Mock Backend Client の準備
    mock_backend_client = AsyncMock()

    # 3. Server の初期化
    server = DataPlaneServer(registry=mock_registry, backend_client=mock_backend_client)

    # 4. AIエージェントからのリクエストをシミュレート
    # (IDが 'client-id-999'、未知のパラメータ 'extra_field' が含まれているとする)
    incoming_request = {
        "jsonrpc": "2.0",
        "id": "client-id-999",
        "method": "tools/call",
        "params": {
            "name": "serverA_read_file",
            "arguments": {"path": "/etc/passwd"},
            "extra_field": "should_be_preserved" # ペイロード干渉をしないなら維持されるべき
        }
    }

    # 5. 転送処理を実行
    await server._forward_to_backend(incoming_request)

    # 6. バックエンドに正しく横流しされたかを検証
    mock_backend_client.forward_request.assert_called_once()
    
    # 呼び出された際の引数を取得
    called_route, forwarded_req = mock_backend_client.forward_request.call_args[0]

    # ルーティング先が正しいか
    assert called_route == "/mcp/serverA"

    # ★最重要: ペイロードが破壊されていないか（Pure Proxyの証明）
    assert forwarded_req["id"] == "client-id-999", "ID must be preserved"
    assert forwarded_req["params"]["name"] == "read_file", "Tool name must be translated to backend name"
    assert forwarded_req["params"]["arguments"] == {"path": "/etc/passwd"}, "Arguments must be preserved"
    assert forwarded_req["params"]["extra_field"] == "should_be_preserved", "Unknown fields must be preserved"

@pytest.mark.anyio
async def test_forward_cancellation_to_backend():
    """AIからの実行キャンセル通知が、正しいバックエンドへ転送されることを検証"""
    mock_registry = MagicMock()
    mock_registry.get_tool_routing_info.return_value = {
        "target_route": "/mcp/serverB",
        "backend_tool_name": "long_task"
    }
    mock_backend_client = AsyncMock()
    server = DataPlaneServer(registry=mock_registry, backend_client=mock_backend_client)

    # 1. ツール呼び出し (GatewayがIDとルートの対応を記憶する)
    call_req = {"jsonrpc": "2.0", "id": "cancel-123", "method": "tools/call", "params": {"name": "serverB_long_task"}}
    await server._handle_message(json.dumps(call_req))

    # 2. キャンセル通知の送信 (AIから)
    cancel_req = {"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {"requestId": "cancel-123"}}
    await server._handle_message(json.dumps(cancel_req))

    # 検証: 1回目の呼び出しと2回目のキャンセル通知、計2回転送されていること
    assert mock_backend_client.forward_request.call_count == 2
    route, payload = mock_backend_client.forward_request.call_args_list[1][0]
    
    assert route == "/mcp/serverB"
    assert payload["method"] == "notifications/cancelled"
    assert payload["params"]["requestId"] == "cancel-123"