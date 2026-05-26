"""
text_to_sql.py — 자연어 → SQL 오케스트레이터

【흐름】
  자연어 질문
      │
      ▼
  Claude API (claude-sonnet-4-6)
      │ tool_use 요청
      ▼
  PostgresBackend (MCP 툴과 동일한 로직)
      │ 결과 반환
      ▼
  Claude API (최종 답변 생성)
      │
      ▼
  { answer, sql, rows }
"""
import os
from typing import Optional

import anthropic

from mcp_server.backends.postgres import PostgresBackend

MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """당신은 CRM 데이터 분석 전문가입니다.
사용자 질문을 받아 DB 툴로 스키마를 확인하고 SQL을 실행해 답변하세요.

규칙:
1. list_tables → get_table_schema 순으로 스키마 확인 후 SQL 작성
2. SELECT만 사용, 금액은 원화/천단위 구분자 표시
3. 답변은 한국어로, 실행 SQL을 포함할 것
"""

# Claude에게 노출할 툴 정의
TOOLS = [
    {
        "name": "list_tables",
        "description": "사용 가능한 테이블 목록과 컬럼 요약 반환",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "get_table_schema",
        "description": "테이블의 컬럼·타입·외래키 상세 정보 반환",
        "input_schema": {
            "type": "object",
            "properties": {"table_name": {"type": "string"}},
            "required": ["table_name"],
        },
    },
    {
        "name": "execute_query",
        "description": "SELECT 쿼리 실행 (DML 차단)",
        "input_schema": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
]


class TextToSQLService:

    def __init__(self, backend=None):
        self.client = anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
        self.backend = backend or PostgresBackend()

    async def _call_tool(self, name: str, args: dict) -> str:
        """Claude가 요청한 툴을 PostgresBackend로 실행."""
        import json
        if name == "list_tables":
            tables = await self.backend.list_tables()
            summary = {}
            for t in tables:
                schema = await self.backend.get_table_schema(t)
                summary[t] = [f"{c['column_name']}({c['data_type']})" for c in schema["columns"]]
            return json.dumps(summary, ensure_ascii=False)
        if name == "get_table_schema":
            schema = await self.backend.get_table_schema(args["table_name"])
            return json.dumps(schema, ensure_ascii=False)
        if name == "execute_query":
            result = await self.backend.execute_query(args["query"])
            return json.dumps(result, ensure_ascii=False, default=str)
        return f"알 수 없는 툴: {name}"

    async def query(self, question: str) -> dict:
        """자연어 질문 → {answer, sql, rows} 반환."""
        messages = [{"role": "user", "content": question}]
        executed_sql: Optional[str] = None

        for _ in range(8):
            response = await self.client.messages.create(
                model=MODEL,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "end_turn":
                answer = next((b.text for b in response.content if hasattr(b, "text")), "")
                break

            tool_results = []
            for block in response.content:
                if block.type != "tool_use":
                    continue
                if block.name == "execute_query":
                    executed_sql = block.input.get("query")
                output = await self._call_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
            messages.append({"role": "user", "content": tool_results})
        else:
            answer = "응답 생성에 실패했습니다."

        return {"answer": answer, "sql": executed_sql}
