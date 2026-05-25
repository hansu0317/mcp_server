"""
CRM Text-to-SQL FastAPI 애플리케이션

MCP 서버(mcp_server/server.py)를 subprocess로 시작하고,
Groq LLM이 MCP 툴을 사용해 자연어 → SQL → 결과를 반환한다.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import query, schema
from api.services.mcp_client import mcp_manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[startup] MCP 서버 시작 중...")
    await mcp_manager.start()
    print("[startup] 완료")
    yield
    print("[shutdown] MCP 서버 종료 중...")
    await mcp_manager.stop()


app = FastAPI(
    title="CRM Text-to-SQL API",
    description="자연어로 CRM 데이터를 조회합니다. MCP + Groq/Claude 기반.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(query.router)
app.include_router(schema.router)


@app.get("/health")
async def health():
    return {"status": "ok", "mcp_tools": [t.name for t in mcp_manager.get_tools()]}
