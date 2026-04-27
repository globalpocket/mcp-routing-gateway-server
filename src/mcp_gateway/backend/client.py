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
    def __init__(self, base_url: str = "http://localhost:8000", stdout_callback: Callable[[str], None] = None):
        self.base_url = base_url.rstrip("/")
        # AIエージェントへ直接メッセージを届けるためのコールバック（デフォルトは sys.stdout）
        self.stdout_callback = stdout_callback or self._default_stdout
        self.client = httpx.AsyncClient(timeout=None) # 常時接続のためタイムアウトなし
        self._streams: Dict[str, Dict[str, Any]] = {}

    def _default_stdout(self, message: str):
        sys.stdout.write(message + "\n")
        sys.stdout.flush()

    async def _stream_task(self, target_route: str):
        """特定のバックエンドに対するSSE接続を維持し、受信したメッセージを横流しする"""
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
                            # ★最重要: バックエンドからのJSON-RPCメッセージを、一切手を加えずにAIへ横流し
                            self.stdout_callback(event.data)
                            
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
            
            # ★最重要: リクエストをPOSTで投げる(ファイア・アンド・フォーゲット)。
            # レスポンス待機はせず、上記の _stream_task が受け取ってstdoutに流す。
            asyncio.create_task(self.client.post(post_url, json=req))
            
        except Exception as e:
            logger.error(f"Failed to forward request to {target_route}: {e}")
            error_res = json.dumps({
                "jsonrpc": "2.0",
                "id": req.get("id"),
                "error": {"code": -32000, "message": f"Gateway Forwarding Error: {e}"}
            })
            self.stdout_callback(error_res)

    async def fetch_tools(self, target_route: str) -> List[Dict[str, Any]]:
        """
        (Control Plane用) バックエンドから tools/list を取得する。
        これだけはAIへ横流しせず、Gateway自身がレスポンスを解釈して内部レジストリを作るため、
        独立した一時的な接続を行う。
        """
        sse_url = f"{self.base_url}{target_route}/sse"
        req = {"jsonrpc": "2.0", "id": "internal-fetch", "method": "tools/list", "params": {}}
        
        async with httpx.AsyncClient(timeout=10.0) as temp_client:
            try:
                async with aconnect_sse(temp_client, "GET", sse_url) as event_source:
                    post_endpoint = None
                    async for event in event_source.aiter_sse():
                        if event.event == "endpoint":
                            post_endpoint = event.data
                            break
                    
                    if not post_endpoint: return []
                        
                    post_url = f"{self.base_url}{post_endpoint}" if post_endpoint.startswith("/") else post_endpoint
                    await temp_client.post(post_url, json=req)
                    
                    async for event in event_source.aiter_sse():
                        if event.event == "message":
                            res = json.loads(event.data)
                            if res.get("id") == "internal-fetch":
                                return res.get("result", {}).get("tools", [])
            except Exception as e:
                logger.error(f"Failed to fetch tools from {target_route}: {e}")
        return []
