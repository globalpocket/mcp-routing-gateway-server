import sys
import json
import asyncio
import logging
from typing import Dict, Any, Optional
from mcp_gateway.core.registry import ToolRegistry

logger = logging.getLogger(__name__)

class DataPlaneServer:
    """
    AIエージェントと標準入出力(stdio)経由でJSON-RPC通信を行うサーバー
    (Pure Proxy としてペイロードを透過的にバイパスする)
    """
    def __init__(self, registry: ToolRegistry, backend_client: Any = None):
        self.registry = registry
        self.backend_client = backend_client 
        self._running = False
        # リクエストIDと送信元ルートの対応表（Sampling応答用）
        self._response_routes: Dict[str, str] = {}
        
        # バックエンドからのメッセージをフックして監視する
        if self.backend_client:
            self.backend_client.message_callback = self._handle_backend_message

    def _handle_backend_message(self, message: str, source_route: str):
        """バックエンドからLLMへ送られるメッセージを監視し、IDを記録する"""
        try:
            data = json.loads(message)
            req_id = data.get("id")
            # method が存在する場合は「バックエンドからの要求」
            if req_id is not None and "method" in data:
                self._response_routes[str(req_id)] = source_route
        except Exception:
            pass
        
        # 本来の責務通り、LLMへ透過的に流す
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    async def start(self):
        """標準入力からのJSON-RPCリクエストを非同期で待ち受けるループ"""
        self._running = True
        logger.info("Data Plane Server started. Listening on stdio...")
        
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: protocol, sys.stdin)

        while self._running:
            try:
                line = await reader.readline()
                if not line:
                    break # EOF
                
                await self._handle_message(line.decode('utf-8').strip())
            except Exception as e:
                logger.error(f"Error reading from stdin: {e}")

    async def _handle_message(self, message: str):
        """受信したJSON-RPCメッセージを解析してルーティングする"""
        if not message:
            return

        try:
            req = json.loads(message)
            req_id = req.get("id")
            method = req.get("method")
            params = req.get("params", {})

            # 1. AIからの「応答(レスポンス)」の場合、元のバックエンドへ送り返す
            if req_id is not None and ("result" in req or "error" in req) and method is None:
                await self._forward_response_to_backend(req)
                return

            # 2. Gateway自身が応答すべきメソッド
            if method == "initialize":
                await self._send_response(req_id, self._handle_initialize())
            
            elif method == "tools/list":
                await self._send_response(req_id, self._handle_tools_list())
            
            # 3. バックエンドへバイパス(丸投げ)すべきメソッド
            elif method == "tools/call":
                await self._forward_to_backend(req)
                
            elif req_id is not None:
                await self._send_error(req_id, -32601, f"Method not found: {method}")

        except json.JSONDecodeError:
            await self._send_error(None, -32700, "Parse error")
        except Exception as e:
            logger.error(f"Internal error handling message: {e}")
            # JSONのreq変数が存在しない可能性も考慮
            error_id = req.get("id") if 'req' in locals() and isinstance(req, dict) else None
            await self._send_error(error_id, -32603, f"Internal error: {str(e)}")

    def _handle_initialize(self) -> Dict[str, Any]:
        return {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "mcp-routing-gateway", "version": "0.1.0"}
        }

    def _handle_tools_list(self) -> Dict[str, Any]:
        tools = self.registry.get_tools_for_llm()
        return {"tools": tools}

    async def _forward_to_backend(self, req: Dict[str, Any]):
        """ペイロードのIDや引数を維持したまま、ツール名のみ書き換えてバックエンドへ転送する"""
        tool_name = req.get("params", {}).get("name")
        routing_info = self.registry.get_tool_routing_info(tool_name)
        
        if not routing_info:
            await self._send_error(req.get("id"), -32601, f"Tool not found: {tool_name}")
            return

        req["params"]["name"] = routing_info.get("backend_tool_name", tool_name)
        target_route = routing_info["target_route"]

        if self.backend_client:
            logger.info(f"Forwarding pure payload for '{tool_name}' (as '{req['params']['name']}') to {target_route}")
            await self.backend_client.forward_request(target_route, req)
        else:
            logger.warning("Backend client not configured. Dropping request.")
            await self._send_error(req.get("id"), -32000, "Backend client not configured")

    async def _forward_response_to_backend(self, res: Dict[str, Any]):
        """AIからの応答を、要求を出した元のバックエンドへ送り返す"""
        req_id = str(res.get("id"))
        target_route = self._response_routes.pop(req_id, None) # メモリリーク防止のためポップ
        
        if target_route and self.backend_client:
            logger.info(f"Forwarding AI response for ID {req_id} to {target_route}")
            await self.backend_client.forward_request(target_route, res)
        else:
            logger.warning(f"No routing info found for response ID: {req_id}")

    async def _send_response(self, req_id: Any, result: Dict[str, Any]):
        if req_id is None: return
        response = {"jsonrpc": "2.0", "id": req_id, "result": result}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()

    async def _send_error(self, req_id: Any, code: int, message: str):
        response = {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}
        sys.stdout.write(json.dumps(response) + "\n")
        sys.stdout.flush()