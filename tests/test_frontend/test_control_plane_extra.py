import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
from mcp_gateway.frontend.control_plane import create_admin_api

def test_admin_remove_route():
    """サーバー削除 API の実行とタスク終了を網羅"""
    mock_registry = MagicMock()
    mock_backend = MagicMock()
    app = create_admin_api(mock_registry, mock_backend)
    client = TestClient(app)
    
    response = client.delete("/admin/routes/serverA")
    assert response.status_code == 200
    mock_registry.remove_backend_server.assert_called_with("serverA")
    mock_backend.disconnect.assert_called_with("/mcp/serverA")

def test_admin_sync_route_failure():
    """バックエンドからのツール取得失敗時のエラー処理を網羅"""
    mock_client = AsyncMock()
    mock_client.fetch_tools.side_effect = Exception("Fetch Error")
    
    app = create_admin_api(MagicMock(), mock_client)
    client = TestClient(app)
    
    response = client.post("/admin/routes/sync", json={"server_name": "s", "target_route": "/r"})
    assert response.status_code == 500
    assert "Fetch Error" in response.json()["detail"]