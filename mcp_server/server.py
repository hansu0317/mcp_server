"""
server.py — MCP 서버 진입점

【흐름도】
  Claude Desktop / Claude Code
        │  JSON-RPC 2.0 over stdio
        ▼
  server.py  ←─── 여기
        │  get_backend() 로 백엔드 선택
        ▼
  BaseBackend (추상)
        │
        ├── PostgresBackend  (DB_BACKEND=postgres, 기본값)
        └── DataverseBackend (DB_BACKEND=dataverse, 향후)

환경변수:
  DB_BACKEND = postgres | dataverse  (기본: postgres)
  TAVILY_API_KEY                     (web_search 툴)
"""
import asyncio
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_server.backends import PostgresBackend
from mcp_server.backends.dataverse import DataverseBackend


def get_backend():
    """DB_BACKEND 환경변수로 백엔드를 선택한다."""
    name = os.environ.get("DB_BACKEND", "postgres").lower()
    if name == "dataverse":
        return DataverseBackend()
    return PostgresBackend()


backend = get_backend()

TOOLS = [
    {
        "name": "list_tables",
        "description": "사용 가능한 테이블(엔티티) 목록과 컬럼 요약을 반환합니다.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_schema",
        "description": "특정 테이블의 컬럼·타입·외래키 정보를 반환합니다. SQL 작성 전 반드시 호출하세요.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string", "description": "조회할 테이블명"}},
            "required": ["table_name"],
        },
    },
    {
        "name": "execute_query",
        "description": "읽기 전용 쿼리를 실행하고 결과를 반환합니다. DML(INSERT/UPDATE/DELETE 등)은 차단됩니다.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "실행할 쿼리"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_sample_rows",
        "description": "테이블의 샘플 데이터를 반환합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "web_search",
        "description": "Tavily로 실시간 웹 검색합니다. DB에 없는 외부 정보(시장 동향, 뉴스 등)에 활용하세요.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
]


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def write_json(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def handle_tool(name: str, args: dict) -> dict:

    if name == "list_tables":
        tables = await backend.list_tables()
        # 각 테이블 컬럼 요약도 함께 반환
        summary = {}
        for table in tables:
            schema = await backend.get_table_schema(table)
            summary[table] = [f"{c['column_name']}({c['data_type']})" for c in schema["columns"]]
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False, indent=2)}]}

    if name == "get_table_schema":
        table = args.get("table_name", "")
        tables = await backend.list_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}. 사용 가능: {tables}"}], "isError": True}
        schema = await backend.get_table_schema(table)
        return {"content": [{"type": "text", "text": json.dumps(schema, ensure_ascii=False, indent=2)}]}

    if name == "execute_query":
        try:
            result = await backend.execute_query(args.get("query", ""))
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}]}
        except ValueError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"쿼리 오류: {e}"}], "isError": True}

    if name == "get_sample_rows":
        table = args.get("table_name", "")
        limit = min(int(args.get("limit", 5)), 20)
        tables = await backend.list_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}"}], "isError": True}
        rows = await backend.get_sample_rows(table, limit)
        return {"content": [{"type": "text", "text": json.dumps(rows, ensure_ascii=False, indent=2, default=str)}]}

    if name == "web_search":
        query = args.get("query", "").strip()
        max_results = min(int(args.get("max_results", 5)), 10)
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not query:
            return {"content": [{"type": "text", "text": "검색어가 비어 있습니다."}], "isError": True}
        if not api_key:
            return {"content": [{"type": "text", "text": "TAVILY_API_KEY가 설정되지 않았습니다."}], "isError": True}
        async with httpx.AsyncClient(timeout=15.0, transport=httpx.AsyncHTTPTransport(local_address="0.0.0.0")) as client:
            resp = await client.post(
                "https://api.tavily.com/search",
                json={"api_key": api_key, "query": query, "max_results": max_results},
            )
            resp.raise_for_status()
            data = resp.json()
        results = [
            {"title": r.get("title"), "url": r.get("url"), "content": r.get("content", "")[:500]}
            for r in data.get("results", [])
        ]
        return {"content": [{"type": "text", "text": json.dumps({"query": query, "results": results}, ensure_ascii=False, indent=2)}]}

    return {"content": [{"type": "text", "text": f"알 수 없는 툴: {name}"}], "isError": True}


async def main():
    loop = asyncio.get_event_loop()
    while True:
        try:
            line = await loop.run_in_executor(None, sys.stdin.readline)
            if not line:
                break
            req = json.loads(line)
        except (json.JSONDecodeError, EOFError, ValueError):
            break

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            write_json(_ok(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "crm-mcp-server", "version": "2.0.0"},
            }))
        elif method == "notifications/initialized":
            pass
        elif method == "tools/list":
            write_json(_ok(req_id, {"tools": TOOLS}))
        elif method == "tools/call":
            try:
                result = await handle_tool(params.get("name", ""), params.get("arguments", {}))
                write_json(_ok(req_id, result))
            except Exception as e:
                write_json(_err(req_id, -32000, str(e)))
        elif method == "ping":
            write_json(_ok(req_id, {}))
        else:
            write_json(_err(req_id, -32601, f"Method not found: {method}"))


if __name__ == "__main__":
    asyncio.run(main())
