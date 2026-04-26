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
    # テストの独立性を保つため、設定ファイルを読み込むが
    # explicit_routingによる警告を避けるため、空の設定をシミュレートするなどの工夫も可能
    reg = ToolRegistry("gateway_config.yaml")
    
    # モックサーバー localhost:8000 に接続する設定
    client = BackendClient(base_url="http://127.0.0.1:8000")
    server = DataPlaneServer(registry=reg, backend_client=client)
    
    # スタブサーバーのツールを登録
    reg.add_backend_server("server_mock", [
        {"name": "read_file", "description": "Read info", "inputSchema": {}}
    ])
    return server

@pytest.mark.anyio
async def test_mcp_initialize(setup_gateway, capsys):
    """MCP初期化(initialize)が正しく応答されるか検証"""
    server = setup_gateway  # フィクスチャは既に解決済みなのでawait不要
    req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    
    await server._handle_message(req)
    
    captured = capsys.readouterr()
    assert '"name": "mcp-gateway-server"' in captured.out
    assert '"protocolVersion"' in captured.out

@pytest.mark.anyio
async def test_mcp_tools_list(setup_gateway, capsys):
    """提供可能なツール一覧(tools/list)が正しく返るか検証"""
    server = setup_gateway
    req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    
    await server._handle_message(req)
    
    captured = capsys.readouterr()
    # ベース名とプレフィックス付きの両方が含まれているか
    assert "read_file" in captured.out
    assert "server_mock_read_file" in captured.out

@pytest.mark.anyio
async def test_cli_stdio_to_sse_roundtrip(setup_gateway, capsys):
    """
    Data Plane -> Backend(Mock) -> Data Plane の全行程(tools/call)をテスト。
    """
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
    
    # 転送実行
    await server._handle_message(test_input)

    # SSE経由で結果が戻るのを待機 (Mockサーバーが起動している前提)
    await asyncio.sleep(0.5) 
    
    captured = capsys.readouterr()
    assert "Echo: read_file" in captured.out
    assert '"id": "e2e-test-1"' in captured.out

def test_cli_initialization_flow():
    """src/mcp_gateway/cli.py の起動初期化ロジックのカバレッジを稼ぐ"""
    from mcp_gateway.cli import main
    
    # asyncio.runをモックして製品の無限ループ起動を回避
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(config="gateway_config.yaml")
        
        # 修正ポイント: 
        # asyncio.runに渡されたコルーチン(main_loop)を明示的に閉じる side_effect を設定。
        # これにより、RuntimeWarning（未待機警告）を物理的に解消しつつ、
        # 起動シーケンスが最後まで呼ばれたことを検証できます。
        def close_coro_side_effect(coro):
            coro.close()
            return None

        with patch("asyncio.run", side_effect=close_coro_side_effect) as mock_run:
            # main()を実行。初期化処理が走り、最後にasyncio.run(main_loop())が呼ばれる
            main()
            
            # asyncio.runが呼ばれたこと（＝起動準備が完了したこと）を確認
            mock_run.assert_called_once()