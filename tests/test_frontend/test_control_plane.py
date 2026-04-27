import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from mcp_gateway.frontend.control_plane import create_admin_api

def test_admin_sync_route_calls_registry():
    # Mockの準備
    mock_registry = MagicMock()
    mock_client = AsyncMock()
    # fetch_tools がモックのツールリストを返すように設定
    mock_client.fetch_tools.return_value = [{"name": "fetched_tool"}]
    
    app = create_admin_api(mock_registry, mock_client)
    client = TestClient(app)

    # 実行: /admin/routes/sync へのPOST
    response = client.post("/admin/routes/sync", json={
        "target_server": "test_srv"
    })

    # 検証
    assert response.status_code == 200
    mock_client.fetch_tools.assert_called_once_with("test_srv")
    # API呼び出しによって、Registryのadd_backend_serverが正しく呼ばれたか
    mock_registry.add_backend_server.assert_called_once_with("test_srv", [{"name": "fetched_tool"}])