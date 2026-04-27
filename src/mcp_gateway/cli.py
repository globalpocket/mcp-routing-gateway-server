import sys
import argparse
import asyncio
import logging
import uvicorn
import os
from mcp_gateway.core.registry import ToolRegistry
from mcp_gateway.backend.client import BackendClient
from mcp_gateway.frontend.data_plane import DataPlaneServer
from mcp_gateway.frontend.control_plane import create_admin_api

# 標準出力はAIエージェントとの通信（JSON-RPC）に占有されるため、
# アプリケーションのログはすべて標準エラー出力（stderr）に流す
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger(__name__)

async def run_admin_api(app):
    """FastAPIを非同期タスクとして起動するラッパー"""
    # ログがAIエージェントの通信(stdout)を汚染しないよう、アクセスログは無効化(またはstderr化)する
    config = uvicorn.Config(app, host="127.0.0.1", port=8001, access_log=False, log_level="warning")
    server = uvicorn.Server(config)
    logger.info("Control Plane Server started. Listening on http://127.0.0.1:8001")
    await server.serve()

def main():
    parser = argparse.ArgumentParser(description="MCP Routing Gateway")
    parser.add_argument(
        "--config", 
        default="gateway_config.yaml", 
        help="Path to the gateway configuration YAML file (default: gateway_config.yaml)"
    )
    args = parser.parse_args()

    logger.info(f"Starting MCP Routing Gateway. Loading config from {args.config}")
    
    # 1. Registryの初期化と設定読み込み
    registry = ToolRegistry(args.config)
    logger.info("Registry initialized. Waiting for dynamic tool registrations via Control Plane.")
    
    # 2. Backend Client の初期化 (環境変数から取得し、デフォルトをlocalhostにする)
    backend_base_url = os.getenv("MCP_BACKEND_BASE_URL", "http://localhost:8000")
    backend_client = BackendClient(base_url=backend_base_url)

    # 3. Data Plane と Control Plane サーバーの初期化
    data_plane = DataPlaneServer(registry=registry, backend_client=backend_client)
    admin_app = create_admin_api(registry=registry, backend_client=backend_client)

    # 4. 非同期ループで通信を開始 (Data Plane と Control Plane を並行稼働)
    async def main_loop():
        await asyncio.gather(
            data_plane.start(),
            run_admin_api(admin_app)
        )

    try:
        asyncio.run(main_loop())
    except KeyboardInterrupt:
        logger.info("Gateway stopped by user (KeyboardInterrupt).")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()