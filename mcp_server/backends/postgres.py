"""
postgres.py — PostgreSQL 백엔드 구현

【흐름】
  server.py → PostgresBackend → asyncpg → PostgreSQL

환경변수:
  DATABASE_URL = postgresql://user:pass@host:port/dbname
"""
import os
import re
from typing import Optional

import asyncpg

from .base import BaseBackend

_DANGEROUS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|TRUNCATE|ALTER|CREATE|GRANT|REVOKE)\b",
    re.IGNORECASE,
)

_pool: Optional[asyncpg.Pool] = None


async def _get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["DATABASE_URL"], min_size=2, max_size=10)
    return _pool


class PostgresBackend(BaseBackend):

    async def list_tables(self) -> list[str]:
        """public 스키마의 테이블 목록을 DB에서 동적으로 조회."""
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
            )
        return [r["table_name"] for r in rows]

    async def get_table_schema(self, table_name: str) -> dict:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            cols = await conn.fetch(
                "SELECT column_name, data_type, is_nullable, column_default "
                "FROM information_schema.columns "
                "WHERE table_name=$1 AND table_schema='public' ORDER BY ordinal_position",
                table_name,
            )
            fks = await conn.fetch(
                "SELECT kcu.column_name, ccu.table_name AS ref_table, ccu.column_name AS ref_column "
                "FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name=ccu.constraint_name "
                "WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_name=$1",
                table_name,
            )
        return {"table": table_name, "columns": [dict(r) for r in cols], "foreign_keys": [dict(r) for r in fks]}

    async def execute_query(self, query: str) -> dict:
        """SELECT만 허용. DML/DDL은 차단."""
        if _DANGEROUS.search(query):
            raise ValueError("읽기 전용 쿼리만 허용됩니다.")
        if not re.search(r"\bSELECT\b", query, re.IGNORECASE):
            raise ValueError("SELECT 구문이 없습니다.")
        max_rows = int(os.environ.get("MAX_QUERY_ROWS", 100))
        if not re.search(r"\bLIMIT\b", query, re.IGNORECASE):
            query = f"{query} LIMIT {max_rows}"
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
        result = [dict(r) for r in rows]
        return {"row_count": len(result), "rows": result}

    async def get_sample_rows(self, table_name: str, limit: int) -> list:
        pool = await _get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(f"SELECT * FROM {table_name} LIMIT $1", limit)
        return [dict(r) for r in rows]
