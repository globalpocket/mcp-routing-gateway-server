import yaml
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    静的設定(YAML)の読み込みと、複数MCPサーバーからのツールマージ・競合解決を行う
    """
    def __init__(self, config_path: str):
        self.config_path = config_path
        self.config = self._load_yaml(config_path)
        # 最終的にAIに提示し、ルーティングに使用するツールの辞書
        self.active_tools: Dict[str, Dict[str, Any]] = {}
        # 現在登録されている各バックエンドの生ツールリストを保持する状態マップ
        self._backend_tools_map: Dict[str, List[Dict[str, Any]]] = {}

    def _load_yaml(self, path: str) -> Dict[str, Any]:
        """YAMLファイルを読み込む。重複するキーはPyYAMLの仕様で自動的に後勝ちになる"""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            return {}

    def add_backend_server(self, server_name: str, raw_tools: List[Dict[str, Any]]):
        """(Control Plane用) 動的にサーバーを追加・更新し、ルーティングを再計算する"""
        self._backend_tools_map[server_name] = raw_tools
        self.merge_and_resolve_tools(self._backend_tools_map)
        logger.info(f"Added/Updated server '{server_name}'. Total active tools: {len(self.active_tools)}")

    def remove_backend_server(self, server_name: str):
        """(Control Plane用) 動的にサーバーを削除し、ルーティングを再計算する"""
        if server_name in self._backend_tools_map:
            del self._backend_tools_map[server_name]
            self.merge_and_resolve_tools(self._backend_tools_map)
            logger.info(f"Removed server '{server_name}'. Total active tools: {len(self.active_tools)}")

    def merge_and_resolve_tools(self, backend_tools_map: Dict[str, List[Dict[str, Any]]]):
        """
        各バックエンドから取得したツールリストを結合し、競合を解決する。
        backend_tools_map の例: 
        {
            "serverA": [{"name": "read_file", "description": "..."}, ...],
            "serverB": [{"name": "read_file", "description": "..."}, ...]
        }
        """
        resolved_tools = {}

        # 1. プレフィックス付き登録 ＆ 暗黙のベース名（後勝ち）登録
        for server_name, raw_tools in backend_tools_map.items():
            for raw_tool in raw_tools:
                base_tool_name = raw_tool["name"]
                
                # A. プレフィックス付きツールを常に作成 (例: serverA_read_file)
                namespaced_name = f"{server_name}_{base_tool_name}"
                namespaced_tool = raw_tool.copy()
                namespaced_tool["name"] = namespaced_name
                # AIには見せない内部ルーティング用メタデータ
                namespaced_tool["_target_route"] = f"/mcp/{server_name}"
                resolved_tools[namespaced_name] = namespaced_tool
                
                # B. ベース名での登録 (ループの順序により、偶然重複した場合は後勝ちになる)
                resolved_tools[base_tool_name] = self._create_proxy_tool(base_tool_name, server_name, raw_tool)

        # 2. explicit_routing (明示的なオーバーライド) の適用 [優先度: 高]
        explicit_routing = self.config.get("explicit_routing", {})
        for base_tool_name, target_server in explicit_routing.items():
            target_raw_tool = self._get_raw_tool(backend_tools_map, target_server, base_tool_name)
            if target_raw_tool:
                resolved_tools[base_tool_name] = self._create_proxy_tool(base_tool_name, target_server, target_raw_tool)
                logger.info(f"Explicitly routed '{base_tool_name}' to {target_server}")
            else:
                logger.warning(f"Explicit routing failed: Server '{target_server}' does not have tool '{base_tool_name}'")

        # 3. 仮想ツール(Facade) への置き換え [優先度: 最高]
        self.active_tools = self._apply_virtual_tool_replacements(resolved_tools)


    def _create_proxy_tool(self, tool_name: str, target_server: str, raw_tool: Dict[str, Any]) -> Dict[str, Any]:
        """バックエンドのツールをベース名で呼び出せるようにプロキシ化する"""
        proxy_tool = raw_tool.copy()
        proxy_tool["name"] = tool_name
        proxy_tool["_target_route"] = f"/mcp/{target_server}"
        proxy_tool["_backend_tool_name"] = raw_tool["name"]
        return proxy_tool

    def _get_raw_tool(self, backend_tools_map: Dict[str, List[Dict[str, Any]]], server_name: str, tool_name: str) -> Optional[Dict[str, Any]]:
        """特定のサーバーから特定のツール定義を検索する"""
        tools = backend_tools_map.get(server_name, [])
        for tool in tools:
            if tool["name"] == tool_name:
                return tool
        return None

    def _apply_virtual_tool_replacements(self, resolved_tools: Dict[str, Any]) -> Dict[str, Any]:
        """静的設定に定義された仮想ツールをマージ・上書きする"""
        virtual_tools_config = self.config.get("virtual_tools", {})
        final_tools = resolved_tools.copy()

        for v_name, v_config in virtual_tools_config.items():
            # 仮想ツールのスキーマ定義（バックエンドの実体を隠蔽）
            virtual_tool = {
                "name": v_name,
                "description": v_config.get("description", ""),
                "inputSchema": v_config.get("inputSchema", {"type": "object", "properties": {}}),
                "_target_route": v_config.get("target_route")
            }
            final_tools[v_name] = virtual_tool
            logger.info(f"Registered virtual tool: {v_name}")

        return final_tools

    def get_tools_for_llm(self) -> List[Dict[str, Any]]:
        """Data Plane (stdio) が AIエージェントに返すためのクリーンなツールリストを生成"""
        llm_tools = []
        for tool in self.active_tools.values():
            clean_tool = tool.copy()
            # アンダースコア(_)で始まる内部用のメタデータを取り除き、純粋なMCPフォーマットにする
            clean_tool = {k: v for k, v in clean_tool.items() if not k.startswith("_")}
            llm_tools.append(clean_tool)
        return llm_tools

    def get_tool_routing_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Data Plane (stdio) がリクエストをルーティングする際に内部情報を取得する"""
        tool = self.active_tools.get(tool_name)
        if not tool:
            return None
        return {
            "target_route": tool.get("_target_route"),
            "backend_tool_name": tool.get("_backend_tool_name", tool_name)
        }