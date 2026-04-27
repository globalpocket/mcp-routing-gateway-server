import json
import logging
from typing import Dict, Any, List
from contextlib import AsyncExitStack
import mcp.types as types
from mcp.client.session import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

logger = logging.getLogger(__name__)

class BackendClient:
    """
    mcp_config.json に定義された複数のバックエンドMCPサーバー(stdio起動)を
    公式SDKを利用して一括管理・接続維持するクライアントマネージャー。
    """
    def __init__(self, mcp_config_path: str = "mcp_config.json"):
        self.mcp_config_path = mcp_config_path
        self.sessions: Dict[str, ClientSession] = {}
        self._exit_stack = AsyncExitStack()

    async def start(self):
        """設定ファイルを読み込み、定義されているすべてのサーバープロセスを起動・接続する"""
        try:
            with open(self.mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {self.mcp_config_path}. Starting without backends.")
            return
        except Exception as e:
            logger.error(f"Failed to load {self.mcp_config_path}: {e}")
            return

        servers = config.get("mcpServers", {})
        for server_name, server_config in servers.items():
            await self._connect_server(server_name, server_config)

    async def _connect_server(self, server_name: str, config: Dict[str, Any]):
        """個別のMCPサーバーをサブプロセスとして起動し、セッションを保持する"""
        try:
            command = config.get("command")
            args = config.get("args", [])
            env = config.get("env", None)
            
            if not command:
                logger.error(f"Server '{server_name}' is missing 'command' in config.")
                return

            server_params = StdioServerParameters(command=command, args=args, env=env)
            
            # stdio パイプの確立 (AsyncExitStackでライフサイクルを自動管理)
            stdio_transport = await self._exit_stack.enter_async_context(stdio_client(server_params))
            read_stream, write_stream = stdio_transport
            
            # セッションの確立と初期化
            session = await self._exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
            await session.initialize()
            
            self.sessions[server_name] = session
            logger.info(f"Successfully connected to backend server: {server_name}")
        except Exception as e:
            logger.error(f"Failed to connect to backend server '{server_name}': {e}")

    async def stop(self):
        """すべてのバックエンドプロセスを安全に終了させる"""
        await self._exit_stack.aclose()
        self.sessions.clear()
        logger.info("All backend connections closed.")

    async def call_tool(self, target_server: str, tool_name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """フロントエンド(Data Plane)からのツール呼び出し要求を、該当バックエンドへ中継する"""
        session = self.sessions.get(target_server)
        if not session:
            raise ValueError(f"Backend server '{target_server}' is not connected or does not exist.")
        
        logger.info(f"Calling tool '{tool_name}' on backend '{target_server}'")
        result = await session.call_tool(tool_name, arguments)
        return result.content

    async def fetch_tools(self, target_server: str) -> List[Dict[str, Any]]:
        """(Control Plane / 同期用) バックエンドからツール一覧を取得する"""
        session = self.sessions.get(target_server)
        if not session:
            logger.error(f"Backend server '{target_server}' is not connected.")
            return []
        
        try:
            tools_result = await session.list_tools()
            # Registryが処理しやすい辞書のリスト形式に変換
            return [
                {
                    "name": t.name,
                    "description": t.description,
                    "inputSchema": t.inputSchema
                }
                for t in tools_result.tools
            ]
        except Exception as e:
            logger.error(f"Failed to fetch tools from '{target_server}': {e}")
            return []

    def disconnect(self, target_server: str):
        """特定のバックエンドを切断する"""
        if target_server in self.sessions:
            del self.sessions[target_server]
            logger.info(f"Disconnected server '{target_server}' from active sessions.")