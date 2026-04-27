import logging
from typing import Any
import mcp.types as types
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions
from mcp_gateway.core.registry import ToolRegistry

logger = logging.getLogger(__name__)

class DataPlaneServer:
    """
    AIエージェントと標準入出力(stdio)経由で通信を行うMCPフロントエンドサーバー。
    MCP公式SDKを活用し、プロトコル管理を完全に隠蔽しつつ Pure Proxy として振る舞う。
    """
    def __init__(self, registry: ToolRegistry, backend_client: Any = None):
        self.registry = registry
        self.backend_client = backend_client
        self.mcp_server = Server("mcp-routing-gateway")
        
        # 公式SDKのルーターにハンドラを登録
        self.mcp_server.list_tools()(self.handle_list_tools)
        self.mcp_server.call_tool()(self.handle_call_tool)

    async def handle_list_tools(self) -> list[types.Tool]:
        """
        AIからの tools/list 要求に対するハンドラ。
        Registryでフィルタリング・仮想化された安全なツール一覧のみをAIに提示する。
        """
        tools_data = self.registry.get_tools_for_llm()
        tools = []
        for t in tools_data:
            tools.append(
                types.Tool(
                    name=t["name"],
                    description=t.get("description", ""),
                    inputSchema=t.get("inputSchema", {"type": "object", "properties": {}})
                )
            )
        return tools

    async def handle_call_tool(self, name: str, arguments: dict) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
        """
        AIからの tools/call 要求に対するハンドラ。
        ペイロード(引数)には一切干渉せず、適切なバックエンドへパススルー(横流し)する。
        """
        routing_info = self.registry.get_tool_routing_info(name)
        if not routing_info:
            raise ValueError(f"Tool not found or blocked by gateway: {name}")

        target_server = routing_info["target_server"]
        backend_tool_name = routing_info["backend_tool_name"]

        if not self.backend_client:
            raise RuntimeError("Backend client is not configured.")

        logger.info(f"Routing tool call '{name}' to server '{target_server}' as '{backend_tool_name}'")

        # バックエンドクライアントへ処理を委譲し、結果をそのままAIへ返す
        # (※ BackendClient 側も今後のタスクで公式SDKに刷新し、この call_tool インターフェースを実装します)
        result = await self.backend_client.call_tool(target_server, backend_tool_name, arguments)
        return result

    async def start(self):
        """標準入出力ストリームを用いてMCPサーバーを起動する"""
        from mcp.server.stdio import stdio_server
        
        logger.info("Data Plane Server started. Listening on stdio...")
        async with stdio_server() as (read_stream, write_stream):
            await self.mcp_server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="mcp-routing-gateway",
                    server_version="0.1.0",
                    capabilities=self.mcp_server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    )
                )
            )