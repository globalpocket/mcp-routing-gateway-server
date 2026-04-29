import pytest
import tempfile
import json
import os
from mcp_gateway.core.registry import ToolRegistry

# テスト用のダミー設定
TEST_CONFIG = {
    "version": "0.2.3",
    "virtual_tools": {
        "run_command": {
            "description": "Safe sandbox command execution",
            "target_server": "sandbox_server"
        }
    },
    "explicit_routing": {
        "read_file": "serverA"
    },
    "blocked_tools": [
        "search_github",        # ベース名をブロック
        "serverA_run_command"   # プレフィックス付きをブロック
    ]
}

# バックエンドから取得したと想定する生のツールリスト
MOCK_BACKEND_TOOLS = {
    "serverA": [
        {"name": "read_file", "description": "Read file from serverA", "inputSchema": {}},
        {"name": "run_command", "description": "Raw dangerous command on serverA", "inputSchema": {}}
    ],
    "serverB": [
        {"name": "read_file", "description": "Read file from serverB", "inputSchema": {}},
        {"name": "search_github", "description": "Search Github", "inputSchema": {}}
    ]
}

@pytest.fixture
def temp_config_file():
    """テスト用の一時的なJSON設定ファイルを作成する"""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, 'w') as f:
        json.dump(TEST_CONFIG, f)
    yield path
    os.remove(path)

@pytest.fixture
def registry(temp_config_file):
    """初期化済みの ToolRegistry インスタンスを提供する"""
    reg = ToolRegistry(temp_config_file)
    reg.merge_and_resolve_tools(MOCK_BACKEND_TOOLS)
    return reg

def test_namespace_prefix_creation(registry):
    """1. すべてのツールにプレフィックス付きのエイリアスが作成されるか"""
    llm_tools = registry.get_tools_for_llm()
    tool_names = [t["name"] for t in llm_tools]
    
    assert "serverA_read_file" in tool_names
    assert "serverB_read_file" in tool_names
    # serverB_search_github はブロックリストにないので存在すべき
    assert "serverB_search_github" in tool_names

def test_explicit_routing_override(registry):
    """2. explicit_routing による明示的な上書きが機能しているか"""
    # configで "read_file" は "serverA" を使うように指定されている
    routing_info = registry.get_tool_routing_info("read_file")
    
    assert routing_info is not None
    assert routing_info["target_server"] == "serverA"
    
    # LLM向けリストでも、ベース名の read_file が存在することを確認
    llm_tools = registry.get_tools_for_llm()
    base_read_file = next(t for t in llm_tools if t["name"] == "read_file")
    assert base_read_file["description"] == "Read file from serverA"

def test_virtual_tool_replacement(registry):
    """3. virtual_tools による危険なツールの安全な置換が機能しているか"""
    # serverA には生の "run_command" があるが、仮想ツールで上書きされるはず
    routing_info = registry.get_tool_routing_info("run_command")
    
    assert routing_info is not None
    # ルーティング先が仮想ツールで定義した sandbox_server になっているか
    assert routing_info["target_server"] == "sandbox_server"

    llm_tools = registry.get_tools_for_llm()
    run_cmd = next(t for t in llm_tools if t["name"] == "run_command")
    # 説明文が仮想ツールのものに差し替わっているか
    assert run_cmd["description"] == "Safe sandbox command execution"

def test_get_tools_for_llm_hides_metadata(registry):
    """4. LLMに返すツールリストから内部メタデータ(_target_server等)が隠蔽されているか"""
    llm_tools = registry.get_tools_for_llm()
    
    for tool in llm_tools:
        # "_" で始まるキーが含まれていないことを確認
        assert not any(key.startswith("_") for key in tool.keys())
        assert "name" in tool
        assert "description" in tool

def test_deterministic_routing_alphabetical_order(temp_config_file):
    """5. 辞書の挿入順序に関わらず、アルファベット順による決定的なルーティングが行われるか"""
    reg = ToolRegistry(temp_config_file)
    
    # 辞書の挿入順序をあえて「Zが先、Aが後」にしてマージを試みる
    unordered_tools_map = {
        "serverZ": [{"name": "shared_tool", "description": "From Z", "inputSchema": {}}],
        "serverA": [{"name": "shared_tool", "description": "From A", "inputSchema": {}}]
    }
    
    reg.merge_and_resolve_tools(unordered_tools_map)
    llm_tools = reg.get_tools_for_llm()
    
    shared = next(t for t in llm_tools if t["name"] == "shared_tool")
    # sorted() 処理により、['serverA', 'serverZ'] の順で評価されるため、必ず Z が後勝ちになる
    assert shared["description"] == "From Z"

def test_explicit_filtering_blocks_tools(registry):
    """6. blocked_tools によって指定されたツールが正しく隠蔽されているか検証"""
    llm_tools = registry.get_tools_for_llm()
    tool_names = [t["name"] for t in llm_tools]
    
    # search_github はベース名としてブロックリストに登録されているため、除外されているべき
    assert "search_github" not in tool_names
    
    # serverA_run_command はプレフィックス付きでブロックリストに登録されているため、除外されているべき
    assert "serverA_run_command" not in tool_names
    
    # AI向けに返されないだけでなく、ルーティング情報からも完全に消えていることを確認
    assert registry.get_tool_routing_info("search_github") is None
    assert registry.get_tool_routing_info("serverA_run_command") is None