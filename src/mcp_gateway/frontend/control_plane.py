import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from mcp_gateway.core.registry import ToolRegistry
from mcp_gateway.backend.client import BackendClient

logger = logging.getLogger(__name__)

class SyncRequest(BaseModel):
    server_name: str
    target_route: str

def create_admin_api(registry: ToolRegistry, backend_client: BackendClient) -> FastAPI:
    """Control Plane (管理用REST API) のFastAPIアプリケーションを生成する"""
    app = FastAPI(title="MCP Gateway Admin API")

    @app.post("/admin/routes/sync")
    async def sync_route(req: SyncRequest):
        """バックエンドからツール一覧を取得し、Registryを動的に更新する"""
        try:
            # 1. バックエンドから最新のツール一覧を取得
            tools = await backend_client.fetch_tools(req.target_route)
            
            # 2. Registryを更新
            registry.add_backend_server(req.server_name, tools)
            
            return {"status": "success", "server_name": req.server_name, "tools_count": len(tools)}
        except Exception as e:
            logger.error(f"Sync failed for {req.server_name}: {e}")
            raise HTTPException(status_code=500, detail=str(e))

    @app.delete("/admin/routes/{server_name}")
    async def remove_route(server_name: str):
        """指定されたサーバーをRegistryから削除する"""
        registry.remove_backend_server(server_name)
        return {"status": "success", "message": f"Server '{server_name}' removed"}

    return app