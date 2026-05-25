"""
CRM MCP Server — JSON-RPC 2.0 over stdio

MCP 프로토콜을 직접 구현 (mcp SDK 불필요, Python 3.9 호환).
FastAPI 시작 시 subprocess로 실행된다.

프로토콜 흐름:
  Client → {"jsonrpc":"2.0","method":"initialize",...}    → Server
  Client → {"jsonrpc":"2.0","method":"tools/list",...}    → Server
  Client → {"jsonrpc":"2.0","method":"tools/call",...}    → Server
"""
import asyncio
import json
import re
import os
import sys

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from mcp_server.database import get_pool

CRM_TABLES = ["customers", "contacts", "deals", "deal_products", "products", "activities"]

_DANGEROUS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

TOOLS = [
    {
        "name": "list_crm_tables",
        "description": "CRM 시스템에서 사용 가능한 테이블 목록과 각 테이블의 한 줄 설명을 반환합니다.",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_schema",
        "description": "특정 테이블의 컬럼명, 데이터 타입, 외래키 관계를 반환합니다. SQL 작성 전 반드시 호출하세요.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "table_name": {"type": "string", "enum": CRM_TABLES}
            },
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
                "table_name": {"type": "string", "enum": CRM_TABLES},
                "limit": {"type": "integer", "default": 5},
            },
            "required": ["table_name"],
        },
    },
]


def _ok(req_id, result):
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id, code, message):
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


async def handle_tool(name: str, arguments: dict) -> dict:
    pool = await get_pool()

    if name == "list_crm_tables":
        return {
            "content": [{"type": "text", "text": json.dumps({
                "customers": "고객사(회사) — 업종, 연매출, 임직원 수",
                "contacts": "고객사 담당자(개인) — 이메일, 직책, 주요 연락처 여부",
                "deals": "영업 기회 — stage(prospecting/qualification/proposal/negotiation/closed_won/closed_lost), 금액, 담당 영업사원",
                "deal_products": "딜에 포함된 제품/수량/단가 (deals ↔ products 다대다)",
                "products": "판매 제품/서비스 — 카테고리, 단가",
                "activities": "영업 활동 이력 — type(call/email/meeting/note), 발생일시",
            }, ensure_ascii=False, indent=2)}]
        }

    if name == "get_table_schema":
        table = arguments.get("table_name", "")
        if table not in CRM_TABLES:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}"}], "isError": True}

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
        if table not in CRM_TABLES:
            return {"content": [{"type": "text", "text": f"알 수 없는 테이블: {table}"}], "isError": True}

        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {table} LIMIT $1", limit)
            result = [dict(r) for r in rows]
            return {"content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}]}

    return {"content": [{"type": "text", "text": f"알 수 없는 툴: {name}"}], "isError": True}


async def main():
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    loop = asyncio.get_event_loop()
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)
    write_transport, _ = await loop.connect_write_pipe(asyncio.BaseProtocol, sys.stdout)

    async def write_json(obj):
        line = json.dumps(obj, ensure_ascii=False) + "\n"
        write_transport.write(line.encode())

    while True:
        try:
            line = await reader.readline()
            if not line:
                break
            req = json.loads(line.decode())
        except (json.JSONDecodeError, EOFError):
            break

        req_id = req.get("id")
        method = req.get("method", "")
        params = req.get("params", {})

        if method == "initialize":
            await write_json(_ok(req_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "crm-database", "version": "1.0.0"},
            }))

        elif method == "notifications/initialized":
            pass  # 응답 불필요

        elif method == "tools/list":
            await write_json(_ok(req_id, {"tools": TOOLS}))

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            try:
                result = await handle_tool(tool_name, arguments)
                await write_json(_ok(req_id, result))
            except Exception as e:
                await write_json(_err(req_id, -32000, str(e)))

        elif method == "ping":
            await write_json(_ok(req_id, {}))

        else:
            await write_json(_err(req_id, -32601, f"Method not found: {method}"))


if __name__ == "__main__":
    asyncio.run(main())
