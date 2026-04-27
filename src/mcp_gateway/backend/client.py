import sys
import json
import asyncio
import logging
import httpx
from httpx_sse import aconnect_sse
from typing import Dict, Any, List, Callable

logger = logging.getLogger(__name__)

class BackendClient:
    """
    リバースプロキシ(Nginx, Traefik, Kong等)経由で背後のMCPサーバーと通信するマルチプレクサ。
    SSEストリームを常時接続し、バックエンドからのイベントを透過的に標準出力へ流す。
    """
    def __init__(self, base_url: str = "http://localhost:8000", message_callback: Callable[[str, str], None] = None, stdout_callback: Callable[[str], None] = None):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(timeout=None) # 常時接続のためタイムアウトなし
        self._streams: Dict[str, Dict[str, Any]] = {}
        
        # 既存テストや旧仕様(stdout_callbackのみ利用)との互換性を保つ
        if stdout_callback and not message_callback:
            self.message_callback = lambda msg, route: stdout_callback(msg)
        else:
            self.message_callback = message_callback or self._default_message_handler

    def _default_message_handler(self, message: str, route: str):
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    async def _stream_task(self, target_route: str):
        """特定のバックエンドに対するSSE接続を維持し、受信したメッセージを横流しする"""
        # 内部状態が未初期化の場合は初期化（堅牢性の向上とテスト対応）
        if target_route not in self._streams:
            self._streams[target_route] = {"ready": asyncio.Event(), "post_url": None, "task": asyncio.current_task()}
            
        sse_url = f"{self.base_url}{target_route}/sse"
        
        while True:
            try:
                logger.info(f"Connecting to persistent SSE stream: {sse_url}")
                async with aconnect_sse(self.client, "GET", sse_url) as event_source:
                    async for event in event_source.aiter_sse():
                        if event.event == "endpoint":
                            post_endpoint = event.data
                            post_url = f"{self.base_url}{post_endpoint}" if post_endpoint.startswith("/") else post_endpoint
                            self._streams[target_route]["post_url"] = post_url
                            self._streams[target_route]["ready"].set()
                            logger.info(f"Received POST endpoint for {target_route}: {post_url}")
                        
                        elif event.event == "message":
                            # SSE受信データのサニタイズ: 正しいJSON-RPCか軽く検証
                            try:
                                data = json.loads(event.data)
                                if not isinstance(data, dict) or data.get("jsonrpc") != "2.0":
                                    raise ValueError("Missing or invalid 'jsonrpc' field or not a dictionary")
                                # 検証成功時のみコールバック（stdioへの出力）を実行
                                self.message_callback(event.data, target_route)
                            except Exception as e:
                                # try-catchで握りつぶさず、エラーとしてロギングしてstdioへの流出を防ぐ
                                logger.error(f"Invalid message format from backend {target_route}: {e} - Raw data: {event.data}")
                            
            except Exception as e:
                logger.error(f"SSE stream disconnected for {target_route}: {e}")
            
            # 切断された場合は数秒待ってから再接続（回復力）
            await asyncio.sleep(3)

    async def ensure_connected(self, target_route: str) -> str:
        """対象ルートへのSSE接続が確立されているか確認し、POST先のURLを返す"""
        if target_route not in self._streams:
            self._streams[target_route] = {
                "ready": asyncio.Event(),
                "post_url": None,
                "task": asyncio.create_task(self._stream_task(target_route))
            }
        
        # endpointイベントが来てPOST URLが判明するまで待機
        await self._streams[target_route]["ready"].wait()
        return self._streams[target_route]["post_url"]

    async def forward_request(self, target_route: str, req: Dict[str, Any]):
        """AIエージェントからのリクエストをバックエンドへバイパスする"""
        try:
            post_url = await self.ensure_connected(target_route)
            
            # リクエストをPOSTで投げる(ファイア・アンド・フォーゲット)
            asyncio.create_task(self.client.post(post_url, json=req))
            
        except Exception as e:
            logger.error(f"Failed to forward request to {target_route}: {e}")
            error_res = json.dumps({
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32000, "message": f"Gateway Forwarding Error: {e}"}
            })
            self.message_callback(error_res, target_route)

    async def fetch_tools(self, target_route: str) -> List[Dict[str, Any]]:
        """
        (Control Plane用) バックエンドと初期化ハンドシェイクを行い、tools/list を取得する。
        """
        sse_url = f"{self.base_url}{target_route}/sse"
        
        init_req = {
            "jsonrpc": "2.0",
            "id": "internal-init",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-routing-gateway", "version": "0.1.0"}
            }
        }
        init_notif = {"jsonrpc": "2.0", "method": "notifications/initialized"}
        tools_req = {"jsonrpc": "2.0", "id": "internal-fetch", "method": "tools/list", "params": {}}
        
        async with httpx.AsyncClient(timeout=10.0) as temp_client:
            try:
                async with aconnect_sse(temp_client, "GET", sse_url) as event_source:
                    post_url = None
                    
                    async for event in event_source.aiter_sse():
                        if event.event == "endpoint" and not post_url:
                            post_endpoint = event.data
                            post_url = f"{self.base_url}{post_endpoint}" if post_endpoint.startswith("/") else post_endpoint
                            
                            # 1. Initialize Handshake の開始
                            await temp_client.post(post_url, json=init_req)
                            
                        elif event.event == "message" and post_url:
                            res = json.loads(event.data)
                            msg_id = res.get("id")
                            
                            if msg_id == "internal-init":
                                # 2. 初期化完了通知を送信し、続けて tools/list を要求
                                await temp_client.post(post_url, json=init_notif)
                                await temp_client.post(post_url, json=tools_req)
                                
                            elif msg_id == "internal-fetch":
                                # 3. ツール一覧を受信して完了
                                return res.get("result", {}).get("tools", [])
                                
            except Exception as e:
                logger.error(f"Failed to fetch tools from {target_route}: {e}")
        return []

    def disconnect(self, target_route: str):
        """
        (Control Plane用) 特定のバックエンドに対するSSE接続タスクをキャンセルし、
        リソースリークを防ぐためのクリーンアップを行う。
        """
        if target_route in self._streams:
            task = self._streams[target_route].get("task")
            if task and not task.done():
                task.cancel()
            del self._streams[target_route]
            logger.info(f"Disconnected SSE stream and cleaned up resources for {target_route}")