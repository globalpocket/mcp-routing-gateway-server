import pytest
from unittest.mock import MagicMock
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_forward_to_backend_error_paths(capsys):
    # 1. ツールが見つからないパス
    reg = MagicMock()
    reg.get_tool_routing_info.return_value = None
    server = DataPlaneServer(registry=reg)
    await server._forward_to_backend({"id": 1, "params": {"name": "missing"}})
    assert "Tool not found" in capsys.readouterr().out

    # 2. バックエンドクライアントが未設定のパス
    reg.get_tool_routing_info.return_value = {"target_route": "/r", "backend_tool_name": "t"}
    server_no_client = DataPlaneServer(registry=reg, backend_client=None)
    await server_no_client._forward_to_backend({"id": 2, "params": {"name": "t"}})
    assert "Backend client not configured" in capsys.readouterr().out