import pytest
import tempfile
import os
import yaml
from mcp_gateway.core.registry import ToolRegistry

@pytest.fixture
def registry():
    with tempfile.NamedTemporaryFile(suffix=".yaml", mode='w', delete=False) as f:
        yaml.dump({"version": "1.0"}, f)
        temp_path = f.name
    reg = ToolRegistry(temp_path)
    yield reg
    os.remove(temp_path)

def test_add_and_remove_server(registry):
    # 1. サーバーの動的追加
    tools = [{"name": "dynamic_tool", "description": "Dynamic", "inputSchema": {}}]
    registry.add_backend_server("server_new", tools)
    
    llm_tools = registry.get_tools_for_llm()
    names = [t["name"] for t in llm_tools]
    assert "dynamic_tool" in names
    assert "server_new_dynamic_tool" in names

    # 2. サーバーの動的削除 (Tear down)
    registry.remove_backend_server("server_new")
    llm_tools = registry.get_tools_for_llm()
    assert len(llm_tools) == 0