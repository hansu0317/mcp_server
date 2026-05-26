"""
server.py — MCP 서버 진입점

환경변수 MCP_TRANSPORT 로 transport를 선택한다.
  stdio  (기본) — Claude Desktop/Code 로컬 연결
  sse           — PaaS HTTP/SSE 원격 연결 (FastAPI에서 실행)
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from mcp_server.transport import run_stdio, run_sse

if __name__ == "__main__":
    transport = os.environ.get("MCP_TRANSPORT", "stdio").lower()
    if transport == "sse":
        run_sse()  # FastAPI uvicorn에서 실행
    else:
        asyncio.run(run_stdio())
