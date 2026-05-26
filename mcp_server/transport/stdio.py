"""
stdio.py — 로컬 개발용 stdio transport

【흐름】
  Claude Desktop/Code
      │ subprocess (stdin/stdout)
      ▼
  server.py → handle_request() → 결과 반환
"""
import asyncio
import json
import sys

from mcp_server.router import handle_request


async def run_stdio():
    """stdin에서 JSON-RPC 요청을 읽고 stdout에 응답한다."""
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            req = json.loads(line)
        except (json.JSONDecodeError, EOFError):
            break

        response = await handle_request(req)
        if response:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
