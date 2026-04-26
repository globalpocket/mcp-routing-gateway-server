import pytest
import httpx
from unittest.mock import patch
from mcp_gateway.backend.client import BackendClient

@pytest.mark.anyio
async def test_fetch_tools_timeout():
    """バックエンド通信時のタイムアウト処理を網羅"""
    # 存在しないポートに接続させ、意図的に失敗させる
    client = BackendClient(base_url="http://localhost:9999") 
    
    # httpxのタイムアウト設定を極めて短くして、エラー処理のパスを迅速に実行
    with patch("httpx.AsyncClient", return_value=httpx.AsyncClient(timeout=0.01)):
        tools = await client.fetch_tools("/mcp/timeout")
        # 通信失敗時に空リストが返る仕様であることを確認
        assert tools == []