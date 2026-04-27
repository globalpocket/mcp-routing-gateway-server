import pytest
import json
import tempfile
import os
from unittest.mock import patch, AsyncMock, MagicMock
import mcp.types as types
from mcp_gateway.backend.client import BackendClient

@pytest.fixture
def dummy_mcp_config():
    """テスト用の一時的な mcp_config.json を作成"""
    config = {
        "mcpServers": {
            "test_server": {
                "command": "echo",
                "args": ["test"]
            }
        }
    }
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        json.dump(config, f)
    yield path
    os.remove(path)

@pytest.mark.anyio
async def test_backend_client_start_and_connect(dummy_mcp_config):
    """mcp_config.json を読み込み、公式SDK経由でサーバーに接続できるか検証"""
    client = BackendClient(mcp_config_path=dummy_mcp_config)
    
    # 公式SDKの stdio_client と ClientSession をモック化
    mock_stdio_context = AsyncMock()
    mock_stdio_context.__aenter__.return_value = (AsyncMock(), AsyncMock())
    
    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session_context = AsyncMock()
    mock_session_context.__aenter__.return_value = mock_session

    with patch("mcp_gateway.backend.client.stdio_client", return_value=mock_stdio_context):
        with patch("mcp_gateway.backend.client.ClientSession", return_value=mock_session_context):
            # 起動
            await client.start()
            
            assert "test_server" in client.sessions
            assert client.sessions["test_server"] == mock_session
            mock_session.initialize.assert_called_once()
            
            # 終了処理 (AsyncExitStackの解放確認)
            await client.stop()
            assert len(client.sessions) == 0

@pytest.mark.anyio
async def test_backend_client_call_tool():
    """バックエンドへのツール呼び出しが正常に中継され、結果が返るか検証"""
    client = BackendClient()
    mock_session = AsyncMock()
    
    # 返り値のモックを作成
    mock_result = MagicMock()
    mock_result.content = [types.TextContent(type="text", text="success")]
    mock_session.call_tool.return_value = mock_result
    
    client.sessions["target1"] = mock_session
    
    result = await client.call_tool("target1", "my_tool", {"arg": "val"})
    
    assert result[0].text == "success"
    mock_session.call_tool.assert_called_once_with("my_tool", {"arg": "val"})

@pytest.mark.anyio
async def test_backend_client_call_tool_not_found():
    """未接続のサーバーへツール呼び出しを行った際のエラーハンドリングを検証"""
    client = BackendClient()
    with pytest.raises(ValueError, match="is not connected or does not exist"):
        await client.call_tool("missing_server", "tool", {})

@pytest.mark.anyio
async def test_backend_client_fetch_tools():
    """Registry同期用のツールリスト取得機能(fetch_tools)を検証"""
    client = BackendClient()
    mock_session = AsyncMock()
    
    mock_tools_result = MagicMock()
    mock_tool = MagicMock()
    mock_tool.name = "test_tool"
    mock_tool.description = "desc"
    mock_tool.inputSchema = {"type": "object"}
    mock_tools_result.tools = [mock_tool]
    
    mock_session.list_tools.return_value = mock_tools_result
    client.sessions["target2"] = mock_session
    
    tools = await client.fetch_tools("target2")
    assert len(tools) == 1
    assert tools[0]["name"] == "test_tool"
    assert tools[0]["description"] == "desc"

@pytest.mark.anyio
async def test_backend_client_fetch_tools_error():
    """エラーパスの検証"""
    client = BackendClient()
    assert await client.fetch_tools("missing") == []