"""
MCP 클라이언트 — JSON-RPC 2.0 over stdio

MCP 서버를 subprocess로 관리하고, JSON-RPC 요청/응답을 처리한다.
mcp SDK 없이 Python 3.9에서 동작하는 경량 구현.
"""
import asyncio
import json
import os
from pathlib import Path
from typing import List, Any, Optional


class MCPClientManager:
    def __init__(self):
        self._process: Optional[asyncio.subprocess.Process] = None
        self._lock = asyncio.Lock()
        self._req_id = 0
        self._tools: List[dict] = []

    def _next_id(self) -> int:
        self._req_id += 1
        return self._req_id

    async def start(self) -> None:
        server_path = Path(os.environ.get("MCP_SERVER_PATH", "mcp_server/server.py")).resolve()
        self._process = await asyncio.create_subprocess_exec(
            "python3", str(server_path),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )

        # initialize 핸드셰이크
        await self._rpc("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "crm-api", "version": "1.0.0"},
        })
        # initialized 알림 (응답 없음)
        await self._send_notification("notifications/initialized", {})

        # 툴 목록 캐싱
        result = await self._rpc("tools/list", {})
        self._tools = result.get("tools", [])
        print(f"[MCP] 서버 연결 완료 — 툴 {len(self._tools)}개: {[t['name'] for t in self._tools]}")

    async def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self._process.kill()

    async def _send(self, obj: dict) -> None:
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        self._process.stdin.write(line.encode())
        await self._process.stdin.drain()

    async def _recv(self) -> dict:
        line = await self._process.stdout.readline()
        return json.loads(line.decode())

    async def _rpc(self, method: str, params: dict) -> Any:
        async with self._lock:
            req_id = self._next_id()
            await self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            resp = await self._recv()
            if "error" in resp:
                raise RuntimeError(f"MCP 오류: {resp['error']}")
            return resp.get("result", {})

    async def _send_notification(self, method: str, params: dict) -> None:
        async with self._lock:
            await self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def get_tools(self) -> List[dict]:
        return self._tools

    def tools_as_openai_format(self) -> List[dict]:
        """Groq/OpenAI tool calling 형식으로 변환"""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            for t in self._tools
        ]

    async def call_tool(self, name: str, arguments: dict) -> str:
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        parts = []
        for content in result.get("content", []):
            if content.get("type") == "text":
                parts.append(content["text"])
        return "\n".join(parts)


mcp_manager = MCPClientManager()
