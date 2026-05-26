"""
CRM MCP Server — JSON-RPC 2.0 over stdio

MCP 프로토콜을 직접 구현 (mcp SDK 불필요, Python 3.9 호환).
FastAPI 시작 시 subprocess로 실행된다.
"""
import asyncio
import json
import re
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_server.database import get_pool

_DANGEROUS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

# DB에서 테이블 목록을 가져오는 캐시 (첫 호출 시 초기화)
_table_cache: list = []


async def get_public_tables() -> list:
    """public 스키마의 실제 테이블 목록을 DB에서 가져온다 (결과 캐싱)."""
    global _table_cache
    if _table_cache:
        return _table_cache
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
            "ORDER BY table_name"
        )
    _table_cache = [r["table_name"] for r in rows]
    return _table_cache


TOOLS = [
    {
        "name": "list_crm_tables",
        "description": "CRM 시스템에서 사용 가능한 테이블 목록과 각 테이블의 컬럼 요약을 반환합니다.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_schema",
        "description": "특정 테이블의 컬럼명, 데이터 타입, 외래키 관계를 반환합니다. SQL 작성 전 반드시 호출하세요.",
        "inputSchema": {
            "type": "object",
            "properties": {"table_name": {"type": "string", "description": "조회할 테이블명"}},
            "required": ["table_name"],
        },
    },
    {
        "name": "execute_sql",
        "description": (
            "SELECT 쿼리를 실행하고 결과를 JSON으로 반환합니다. "
            "INSERT/UPDATE/DELETE 등 DML은 차단됩니다. 결과는 최대 100행으로 제한됩니다."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"sql": {"type": "string"}},
            "required": ["sql"],
        },
    },
    {
        "name": "get_sample_rows",
        "description": "테이블의 샘플 데이터를 반환합니다. 컬럼값 형식 파악에 활용하세요.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "description": "조회할 테이블명"},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["table_name"],
        },
    },
    {
        "name": "web_search",
        "description": (
            "Tavily를 사용해 인터넷에서 최신 정보를 검색합니다. "
            "CRM DB에 없는 외부 정보(시장 동향, 경쟁사, 뉴스 등)가 필요할 때 사용하세요."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 쿼리"},
                "max_results": {"type": "integer", "default": 5, "description": "최대 결과 수 (1-10)"},
            },
            "required": ["query"],
        },
    },
]


def write_json(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def handle_tool(name: str, arguments: dict) -> dict:
    pool = await get_pool()

    if name == "list_crm_tables":
        tables = await get_public_tables()
        # 각 테이블의 컬럼 요약도 함께 반환
        summary = {}
        async with pool.acquire() as conn:
            for table in tables:
                cols = await conn.fetch(
                    "SELECT column_name, data_type FROM information_schema.columns "
                    "WHERE table_name=$1 AND table_schema='public' ORDER BY ordinal_position",
                    table,
                )
                summary[table] = [f"{r['column_name']}({r['data_type']})" for r in cols]
        return {"content": [{"type": "text", "text": json.dumps(summary, ensure_ascii=False, indent=2)}]}

    if name == "get_table_schema":
        table = arguments.get("table_name", "")
        tables = await get_public_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}. 사용 가능: {tables}"}], "isError": True}
        async with pool.acquire() as conn:
            cols = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name=$1 AND table_schema='public' ORDER BY ordinal_position",
                table,
            )
            fks = await conn.fetch(
                "SELECT kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name "
                "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_name=$1",
                table,
            )
        schema = {"table": table, "columns": [dict(r) for r in cols], "foreign_keys": [dict(r) for r in fks]}
        return {"content": [{"type": "text", "text": json.dumps(schema, ensure_ascii=False, indent=2)}]}

    if name == "execute_sql":
        sql = arguments.get("sql", "").strip()
        if _DANGEROUS.search(sql):
            return {"content": [{"type": "text", "text": "쿼리 거부: SELECT만 허용됩니다."}], "isError": True}
        if not re.search(r"\bSELECT\b", sql, re.IGNORECASE):
            return {"content": [{"type": "text", "text": "쿼리 거부: SELECT 구문이 없습니다."}], "isError": True}
        max_rows = int(os.environ.get("MAX_QUERY_ROWS", 100))
        if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
            sql = f"{sql} LIMIT {max_rows}"
        async with pool.acquire() as conn:
            try:
                rows = await conn.fetch(sql)
                result = [dict(r) for r in rows]
                text = json.dumps({"row_count": len(result), "rows": result}, ensure_ascii=False, indent=2, default=str)
                return {"content": [{"type": "text", "text": text}]}
            except Exception as e:
                return {"content": [{"type": "text", "text": f"SQL 오류: {e}"}], "isError": True}

    if name == "get_sample_rows":
        table = arguments.get("table_name", "")
        limit = min(int(arguments.get("limit", 5)), 20)
        tables = await get_public_tables()
        if table not in tables:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}. 사용 가능: {tables}"}], "isError": True}
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {table} LIMIT $1", limit)
            result = [dict(r) for r in rows]
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}]}

    if name == "web_search":
        query = arguments.get("query", "").strip()
        max_results = min(int(arguments.get("max_results", 5)), 10)
        if not query:
            return {"content": [{"type": "text", "text": "검색어가 비어 있습니다."}], "isError": True}
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key:
            return {"content": [{"type": "text", "text": "TAVILY_API_KEY가 설정되지 않았습니다."}], "isError": True}
        async with httpx.AsyncClient(timeout=15.0) as client:
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
                "serverInfo": {"name": "crm-database", "version": "1.0.0"},
            }))

        elif method == "notifications/initialized":
            pass  # 응답 불필요

        elif method == "tools/list":
            write_json(_ok(req_id, {"tools": TOOLS}))

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = await handle_tool(tool_name, arguments)
                write_json(_ok(req_id, result))
            except Exception as e:
                write_json(_err(req_id, -32000, str(e)))

        elif method == "ping":
            write_json(_ok(req_id, {}))

        else:
            write_json(_err(req_id, -32601, f"Method not found: {method}"))


if __name__ == "__main__":
    asyncio.run(main())
