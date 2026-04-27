import pytest
from unittest.mock import patch, mock_open
from mcp_gateway.core.registry import ToolRegistry

def test_registry_load_json_exception():
    """JSON読み込み時の例外パスを網羅"""
    with patch("builtins.open", side_effect=Exception("Disk Error")):
        reg = ToolRegistry("dummy.json")
        assert reg.config == {}

def test_explicit_routing_failed_log(caplog):
    """明示的ルーティングで対象サーバーにツールがない場合の警告パスを網羅"""
    with patch("mcp_gateway.core.registry.ToolRegistry._load_json", return_value={
        "explicit_routing": {"missing_tool": "serverA"}
    }):
        reg = ToolRegistry("dummy.json")
        # serverA を登録するが missing_tool は持たせない
        reg.add_backend_server("serverA", [{"name": "other", "inputSchema": {}}])
        assert "Explicit routing failed" in caplog.text