import pytest
import asyncio
import json
from unittest.mock import patch, MagicMock
from mcp_gateway.core.registry import ToolRegistry
from mcp_gateway.backend.client import BackendClient
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.fixture
async def setup_gateway():
    """テスト用のGateway環境をセットアップするフィクスチャ"""
    reg = ToolRegistry("gateway_config.yaml")
    
    # conftest.py で立ち上がった本物のモックサーバー(8000番)へ接続
    client = BackendClient(base_url="http://127.0.0.1:8000")
    server = DataPlaneServer(registry=reg, backend_client=client)
    
    # cli.pyからモックを削除したため、テスト側で明示的に登録
    reg.add_backend_server("server_mock", [
        {"name": "read_file", "description": "Read info", "inputSchema": {}}
    ])
    return server

@pytest.mark.anyio
async def test_mcp_initialize(setup_gateway, capsys):
    """MCP初期化(initialize)が正しく応答されるか検証"""
    server = setup_gateway
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    
    await server._handle_message(req)
    
    captured = capsys.readouterr()
    assert '"name": "mcp-routing-gateway"' in captured.out
    assert '"protocolVersion"' in captured.out

@pytest.mark.anyio
async def test_mcp_tools_list(setup_gateway, capsys):
    """提供可能なツール一覧(tools/list)が正しく返るか検証"""
    server = setup_gateway
    req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    
    await server._handle_message(req)
    
    captured = capsys.readouterr()
    assert "read_file" in captured.out
    assert "server_mock_read_file" in captured.out

@pytest.mark.anyio
async def test_cli_stdio_to_sse_roundtrip(setup_gateway, capsys):
    """Data Plane -> Backend(Mock) -> Data Plane の本物の全行程(tools/call)をテスト。"""
    server = setup_gateway
    test_input = json.dumps({
        "jsonrpc": "2.0",
        "id": "e2e-test-1",
        "method": "tools/call",
        "params": {
            "name": "server_mock_read_file",
            "arguments": {"path": "test.txt"}
        }
    })
    
    # 転送実行（バックグラウンドの mock_backend.py へ本物のPOSTリクエストが飛ぶ）
    await server._handle_message(test_input)

    # 実際のネットワーク越しのSSE応答を待つ
    await asyncio.sleep(0.5) 
    
    captured = capsys.readouterr()
    assert "Echo: read_file" in captured.out
    assert '"id": "e2e-test-1"' in captured.out

def test_cli_initialization_flow():
    """src/mcp_gateway/cli.py の起動初期化ロジックのカバレッジを稼ぐ"""
    from mcp_gateway.cli import main
    
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(config="gateway_config.yaml")
        
        def close_coro_side_effect(coro):
            coro.close()
            return None

        with patch("asyncio.run", side_effect=close_coro_side_effect) as mock_run:
            main()
            mock_run.assert_called_once()