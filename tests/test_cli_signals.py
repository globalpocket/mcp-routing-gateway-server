import pytest
import sys
import asyncio
from unittest.mock import patch, MagicMock
from mcp_gateway.cli import main

def test_cli_fatal_error_exit():
    """Fatal error発生時に sys.exit(1) が呼ばれることを確認"""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(config="gateway_config.yaml")
        
        # 40行目の初期化は通し、72行目の asyncio.run で例外を発生させる
        # これにより cli.py の 75-77行目の例外ハンドラが確実に実行される
        with patch("asyncio.run", side_effect=Exception("Fatal Error")):
            with pytest.raises(SystemExit) as e:
                main()
            
            # 終了ステータスが 1 であることを検証
            assert e.value.code == 1

def test_cli_keyboard_interrupt():
    """KeyboardInterrupt発生時に正常終了することを確認"""
    with patch("argparse.ArgumentParser.parse_args") as mock_args:
        mock_args.return_value = MagicMock(config="gateway_config.yaml")
        
        # asyncio.run が呼ばれた際に KeyboardInterrupt を発生させる
        # cli.py 73-74行目のハンドラを通す
        with patch("asyncio.run", side_effect=KeyboardInterrupt):
            # SystemExit が発生せず、関数が正常にリターンすることを検証
            main()