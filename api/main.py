"""
main.py — FastAPI 앱 진입점

엔드포인트:
  GET  /          웹 UI (index.html)
  POST /query     자연어 → SQL → 결과 (API Key 필요)
  GET  /mcp/sse   MCP SSE transport
  GET  /health    헬스체크
"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv

load_dotenv()

from api.routes.query import router as query_router
from mcp_server.transport.sse import router as mcp_router

app = FastAPI(title="CRM MCP PaaS", version="1.0.0")

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(query_router)
app.include_router(mcp_router)


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
