import asyncio
import json
from fastapi import FastAPI, Request
from sse_starlette.sse import EventSourceResponse

app = FastAPI()

# このリストに届いたリクエストを保存し、テストから検証できるようにする
received_requests = []
# SSEで送信待ちのキュー
outbound_queue = asyncio.Queue()

@app.get("/mcp/server_mock/sse")
async def sse_endpoint(request: Request):
    """Gatewayが接続しに来るSSEエンドポイント"""
    async def event_generator():
        # 1. 最初にPOST先を教える 'endpoint' イベントを送信
        yield {
            "event": "endpoint",
            "data": "/mcp/server_mock/messages"
        }
        
        # 2. その後、送信待ちのメッセージがあれば 'message' イベントで流す
        while True:
            if await request.is_disconnected():
                break
            message = await outbound_queue.get()
            yield {
                "event": "message",
                "data": json.dumps(message)
            }
            outbound_queue.task_done()

    return EventSourceResponse(event_generator())

@app.post("/mcp/server_mock/messages")
async def message_endpoint(request: Request):
    """Gatewayからリクエストが転送されてくるエンドポイント"""
    payload = await request.json()
    received_requests.append(payload)
    
    # 透過性の証明として、受け取ったリクエストに対する応答をSSE側に詰め込む
    # (実際のMCPサーバーのように振る舞う)
    response = {
        "jsonrpc": "2.0",
        "id": payload.get("id"),
        "result": {"content": [{"type": "text", "text": f"Echo: {payload['params']['name']}"}]}
    }
    await outbound_queue.put(response)
    return {"status": "accepted"}

if __name__ == "__main__":
    import uvicorn
    # 競合を避けるためマイナーなポート 8765 に変更
    uvicorn.run(app, host="127.0.0.1", port=8765)