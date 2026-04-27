import pytest
import sys
import asyncio
from unittest.mock import patch, MagicMock
from mcp_gateway.cli import main

def test_cli_fatal_error_exit():
    """Fatal error発生時に sys.exit(1) が呼ばれることを確認"""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        # JSON設定ファイルのデフォルト名に修正
        mock_args.return_value = MagicMock(config="gateway_config.json", mcp_config="mcp_config.json")
        
        # モックした asyncio.run に渡されたコルーチンを安全に閉じてから例外を発生させる
        def mock_run_fatal(coro):
            coro.close()
            raise Exception("Fatal Error")
            
        with patch("asyncio.run", side_effect=mock_run_fatal):
            with pytest.raises(SystemExit) as e:
                main()
            
            # 終了ステータスが 1 であることを検証
            assert e.value.code == 1

def test_cli_keyboard_interrupt():
    """KeyboardInterrupt発生時に正常終了することを確認"""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(config="gateway_config.json", mcp_config="mcp_config.json")
        
        # モックした asyncio.run に渡されたコルーチンを安全に閉じてから例外を発生させる
        def mock_run_kb(coro):
            coro.close()
            raise KeyboardInterrupt()
            
        with patch("asyncio.run", side_effect=mock_run_kb):
            # SystemExit が発生せず、関数が正常にリターンすることを検証
            main()