import pytest
import subprocess
import sys
import time
import httpx

@pytest.fixture(scope="session", autouse=True)
def run_mock_backend():
    """
    結合テストセッションの開始時にモックサーバーをバックグラウンドで起動し、
    全テスト終了時に自動でシャットダウンする。
    """
    print("\n[Setup] Starting mock_backend.py on port 8765...")
    
    # サーバーを別プロセスで起動
    process = subprocess.Popen(
        [sys.executable, "tests/integration/mock_backend.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    # サーバーがリクエストを受け付けられるようになるまで待機 (最大5秒)
    server_ready = False
    for _ in range(50):
        try:
            # FastAPIのヘルスチェック (ポートを8765に変更)
            with httpx.Client() as client:
                response = client.get("http://127.0.0.1:8765/docs", timeout=0.1)
                if response.status_code == 200:
                    server_ready = True
                    break
        except Exception:
            time.sleep(0.1)

    if not server_ready:
        process.terminate()
        # 起動に失敗した原因（エラー出力）を取得して表示する
        stdout, stderr = process.communicate(timeout=2)
        raise RuntimeError(f"Mock server failed to start.\n--- STDERR ---\n{stderr}")

    # ------ ここで integration フォルダ内の実際のテストが実行される ------
    yield 
    # --------------------------------------------------------------------

    # テスト終了後のクリーンアップ
    print("\n[Teardown] Shutting down mock_backend.py...")
    process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()