import pytest
from unittest.mock import AsyncMock, MagicMock
import mcp.types as types
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_handle_list_tools_filters_correctly():
    """Registryから取得したツールリストが、正しくMCP公式のToolオブジェクトに変換されるか検証"""
    mock_registry = MagicMock()
    mock_registry.get_tools_for_llm.return_value = [
        {
            "name": "safe_tool", 
            "description": "A safely wrapped tool", 
            "inputSchema": {"type": "object", "properties": {"arg1": {"type": "string"}}}
        }
    ]

    server = DataPlaneServer(registry=mock_registry)
    
    # ハンドラを直接呼び出してテスト
    result = await server.handle_list_tools()
    
    assert len(result) == 1
    assert isinstance(result[0], types.Tool)
    assert result[0].name == "safe_tool"
    assert result[0].description == "A safely wrapped tool"
    assert "arg1" in result[0].inputSchema["properties"]

@pytest.mark.anyio
async def test_handle_call_tool_pass_through():
    """AIからのツール呼び出しが、ペイロード(引数)を維持したままバックエンドへ転送されるか検証(Pure Proxyの証明)"""
    mock_registry = MagicMock()
    # serverA_read_file は、バックエンド serverA の read_file にルーティングされる設定
    mock_registry.get_tool_routing_info.return_value = {
        "target_server": "serverA",
        "backend_tool_name": "read_file"
    }

    mock_backend_client = AsyncMock()
    # バックエンドのモックが返すダミー結果
    expected_result = [types.TextContent(type="text", text="File content")]
    mock_backend_client.call_tool.return_value = expected_result

    server = DataPlaneServer(registry=mock_registry, backend_client=mock_backend_client)

    # 実行 (AIエージェントからの呼び出しをシミュレート)
    arguments = {"path": "/etc/hosts", "extra_flag": True}
    result = await server.handle_call_tool("serverA_read_file", arguments)

    # 検証: バックエンドクライアントの call_tool が正しい引数で呼び出されたか
    mock_backend_client.call_tool.assert_called_once_with(
        "serverA",      # target_server
        "read_file",    # backend_tool_name (元の名前に翻訳されていること)
        arguments       # ペイロードが一切改変されていないこと
    )
    
    # 検証: バックエンドからの結果がそのまま返されているか
    assert result == expected_result

@pytest.mark.anyio
async def test_handle_call_tool_blocked_or_missing():
    """ブロックされたツールや存在しないツールが呼ばれた場合、正しくエラー弾くか検証"""
    mock_registry = MagicMock()
    mock_registry.get_tool_routing_info.return_value = None # ツールが見つからない/ブロックされた状態

    server = DataPlaneServer(registry=mock_registry, backend_client=AsyncMock())

    with pytest.raises(ValueError, match="Tool not found or blocked by gateway: missing_tool"):
        await server.handle_call_tool("missing_tool", {})

@pytest.mark.anyio
async def test_handle_call_tool_no_backend():
    """バックエンドクライアントが未設定の場合のエラー処理を検証"""
    mock_registry = MagicMock()
    mock_registry.get_tool_routing_info.return_value = {
        "target_server": "serverA",
        "backend_tool_name": "read_file"
    }

    # バックエンドを None で初期化
    server = DataPlaneServer(registry=mock_registry, backend_client=None)

    with pytest.raises(RuntimeError, match="Backend client is not configured"):
        await server.handle_call_tool("serverA_read_file", {})