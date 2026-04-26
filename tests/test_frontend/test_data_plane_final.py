import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from mcp_gateway.frontend.data_plane import DataPlaneServer

@pytest.mark.anyio
async def test_data_plane_start_exception(caplog):
    """readline 等で例外が出た際の処理(38-39行目)を網羅"""
    server = DataPlaneServer(registry=MagicMock())
    
    # ループの内側(33行目)で例外を発生させるために、reader.readline をモック
    mock_reader = AsyncMock()
    mock_reader.readline.side_effect = Exception("Read Error")
    
    # start() の初期化部分は正常に通し、ループに入らせる
    with patch("asyncio.StreamReader", return_value=mock_reader):
        with patch("asyncio.get_running_loop", return_value=AsyncMock()):
            # 1回エラーを吐かせた後、無限ループにならないよう _running を False にする
            async def stop_after_error(*args, **kwargs):
                server._running = False
                raise Exception("Read Error")
            
            mock_reader.readline.side_effect = stop_after_error
            
            await server.start()
            
            # 検証: 39行目の logger.error が実行されたか
            assert "Error reading from stdin: Read Error" in caplog.text