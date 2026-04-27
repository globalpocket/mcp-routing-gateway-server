import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp_gateway.core.registry import ToolRegistry
from mcp_gateway.backend.client import BackendClient

logger = logging.getLogger(__name__)

class SyncRequest(BaseModel):
    target_server: str

def create_admin_api(registry: ToolRegistry, backend_client: BackendClient) -> FastAPI:
    """Control Plane (管理用REST API) のFastAPIアプリケーションを生成する"""
    app = FastAPI(title="MCP Routing Gateway Admin API")

    @app.post("/admin/routes/sync")
    async def sync_route(req: SyncRequest):
        """バックエンドからツール一覧を取得し、Registryを動的に更新する"""
        try:
            # 1. バックエンドから最新のツール一覧を取得
            tools = await backend_client.fetch_tools(req.target_server)
            
            # 2. Registryを更新
            registry.add_backend_server(req.target_server, tools)
            
            return {"status": "success", "target_server": req.target_server, "tools_count": len(tools)}
        except Exception as e:
            logger.error(f"Sync failed for {req.target_server}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/admin/routes/{target_server}")
    async def remove_route(target_server: str):
        """指定されたサーバーをRegistryから削除する"""
        registry.remove_backend_server(target_server)
        # バックエンドへの接続セッションもクリーンアップする
        backend_client.disconnect(target_server)
        return {"status": "success", "message": f"Server '{target_server}' removed"}

    return app