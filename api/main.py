"""
main.py — FastAPI 앱 진입점

엔드포인트:
  POST /query       자연어 → SQL → 결과 (API Key 필요)
  GET  /mcp/sse     MCP SSE transport (API Key 필요)
  GET  /health      헬스체크
"""
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

from api.routes.query import router as query_router
from mcp_server.transport.sse import router as mcp_router

app = FastAPI(title="CRM MCP PaaS", version="1.0.0")

app.include_router(query_router)
app.include_router(mcp_router)


@app.get("/health")
async def health():
    return {"status": "ok"}
