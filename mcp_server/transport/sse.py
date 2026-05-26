"""
sse.py — PaaS용 HTTP/SSE transport

【흐름】
  고객 Claude Desktop/Code
      │ HTTP POST /mcp  (JSON-RPC 요청)
      │ GET  /mcp/sse   (Server-Sent Events 스트림)
      ▼
  FastAPI → handle_request() → SSE 응답

【SSE란?】
  서버에서 클라이언트로 단방향 스트리밍. HTTP 연결을 유지하면서
  서버가 이벤트를 push한다. MCP spec에서 원격 transport로 채택.
"""
import asyncio
import json
from typing import AsyncGenerator

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from mcp_server.router import handle_request

router = APIRouter(prefix="/mcp", tags=["mcp"])

# 클라이언트별 응답 큐 (session_id → asyncio.Queue)
_queues: dict[str, asyncio.Queue] = {}


async def _event_stream(session_id: str) -> AsyncGenerator[str, None]:
    """SSE 이벤트 스트림 — 클라이언트가 연결되는 동안 응답을 push한다."""
    queue = asyncio.Queue()
    _queues[session_id] = queue
    try:
        # 연결 확인 이벤트
        yield f"event: connected\ndata: {json.dumps({'session_id': session_id})}\n\n"
        while True:
            message = await asyncio.wait_for(queue.get(), timeout=30.0)
            if message is None:  # 종료 신호
                break
            yield f"data: {json.dumps(message, ensure_ascii=False)}\n\n"
    except asyncio.TimeoutError:
        # 30초 idle이면 keepalive ping 전송
        yield "event: ping\ndata: {}\n\n"
    finally:
        _queues.pop(session_id, None)


@router.get("/sse")
async def mcp_sse(request: Request):
    """SSE 스트림 연결 엔드포인트."""
    session_id = request.headers.get("X-Session-ID", str(id(request)))
    return StreamingResponse(
        _event_stream(session_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/message")
async def mcp_message(request: Request):
    """JSON-RPC 요청을 받아 처리 후 SSE로 응답을 push한다."""
    session_id = request.headers.get("X-Session-ID", "")
    body = await request.json()

    response = await handle_request(body)

    if response and session_id in _queues:
        await _queues[session_id].put(response)

    return {"status": "ok"}
