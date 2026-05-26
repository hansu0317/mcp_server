"""
router.py — JSON-RPC 요청 라우터

stdio/SSE 양쪽에서 공통으로 사용하는 요청 처리 로직.
transport 종류에 무관하게 동일하게 동작한다.
"""
import json
import os

import httpx

from mcp_server.backends import PostgresBackend
from mcp_server.backends.dataverse import DataverseBackend

TOOLS = [
    {
        "name": "list_tables",
        "description": "사용 가능한 테이블(엔티티) 목록과 컬럼 요약을 반환합니다.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_schema",
        "description": "특정 테이블의 컬럼·타입·외래키 정보를 반환합니다.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}},
            "required": ["table_name"],
        },
    },
    {
        "name": "execute_query",
        "description": "읽기 전용 쿼리를 실행합니다. DML은 차단됩니다.",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
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
        "description": "Tavily로 실시간 웹 검색합니다.",
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


def _get_backend():
    name = os.environ.get("DB_BACKEND", "postgres").lower()
    if name == "dataverse":
        return DataverseBackend()
    return PostgresBackend()


_backend = _get_backend()


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def _handle_tool(name: str, args: dict) -> dict:
    if name == "list_tables":
        tables = await _backend.list_tables()
        summary = {}
        for table in tables:
            schema = await _backend.get_table_schema(table)
            summary[table] = [f"{c['column_name']}({c['data_type']})" for c in schema["columns"]]
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False, indent=2)}]}

    if name == "get_table_schema":
        table = args.get("table_name", "")
        tables = await _backend.list_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}"}], "isError": True}
        schema = await _backend.get_table_schema(table)
        return {"content": [{"type": "text", "text": json.dumps(schema, ensure_ascii=False, indent=2)}]}

    if name == "execute_query":
        try:
            result = await _backend.execute_query(args.get("query", ""))
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}]}
        except ValueError as e:
            return {"content": [{"type": "text", "text": str(e)}], "isError": True}
        except Exception as e:
            return {"content": [{"type": "text", "text": f"쿼리 오류: {e}"}], "isError": True}

    if name == "get_sample_rows":
        table = args.get("table_name", "")
        limit = min(int(args.get("limit", 5)), 20)
        tables = await _backend.list_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}"}], "isError": True}
        rows = await _backend.get_sample_rows(table, limit)
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


async def handle_request(req: dict) -> dict | None:
    """JSON-RPC 요청을 처리하고 응답을 반환한다. 알림(notification)은 None 반환."""
    req_id = req.get("id")
    method = req.get("method", "")
    params = req.get("params", {})

    if method == "initialize":
        return _ok(req_id, {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "crm-mcp-server", "version": "2.0.0"},
        })
    if method == "notifications/initialized":
        return None  # 알림 — 응답 없음
    if method == "tools/list":
        return _ok(req_id, {"tools": TOOLS})
    if method == "tools/call":
        try:
            result = await _handle_tool(params.get("name", ""), params.get("arguments", {}))
            return _ok(req_id, result)
        except Exception as e:
            return _err(req_id, -32000, str(e))
    if method == "ping":
        return _ok(req_id, {})

    return _err(req_id, -32601, f"Method not found: {method}")
