"""
text_to_sql.py — 자연어 → SQL 오케스트레이터

【흐름】
  자연어 질문
      │
      ▼
  Groq API (llama-3.3-70b-versatile)
      │ tool_calls 요청
      ▼
  PostgresBackend (MCP 툴과 동일한 로직)
      │ 결과 반환
      ▼
  Groq API (최종 답변 생성)
      │
      ▼
  { answer, sql }
"""
import os
import json
from typing import Optional

from groq import AsyncGroq

from mcp_server.backends.postgres import PostgresBackend

MODEL = "llama-3.3-70b-versatile"

SYSTEM_PROMPT = """당신은 CRM 데이터 분석 전문가입니다.
사용자 질문을 받아 DB 툴로 스키마를 확인하고 SQL을 실행해 답변하세요.

규칙:
1. list_tables → get_table_schema 순으로 스키마 확인 후 SQL 작성
2. SELECT만 사용, 금액은 원화/천단위 구분자 표시
3. 답변은 한국어로, 실행 SQL을 포함할 것
"""

# Groq에게 노출할 툴 정의 (OpenAI 호환 형식)
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "사용 가능한 테이블 목록과 컬럼 요약 반환",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_table_schema",
            "description": "테이블의 컬럼·타입·외래키 상세 정보 반환",
            "parameters": {
                "type": "object",
                "properties": {"table_name": {"type": "string"}},
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "execute_query",
            "description": "SELECT 쿼리 실행 (DML 차단)",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
]

# 서비스 인스턴스 — 첫 요청 시 생성 (환경변수 로딩 후)
_service: Optional["TextToSQLService"] = None


def get_service() -> "TextToSQLService":
    global _service
    if _service is None:
        _service = TextToSQLService()
    return _service


class TextToSQLService:

    def __init__(self, backend=None):
        self.client = AsyncGroq(api_key=os.environ["GROQ_API_KEY"])
        self.backend = backend or PostgresBackend()

    async def _call_tool(self, name: str, args: dict) -> str:
        """Groq가 요청한 툴을 PostgresBackend로 실행."""
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
            try:
                result = await self.backend.execute_query(args["query"])
                return json.dumps(result, ensure_ascii=False, default=str)
            except Exception as e:
                return json.dumps({"error": str(e)}, ensure_ascii=False)
        return f"알 수 없는 툴: {name}"

    async def query(self, question: str) -> dict:
        """자연어 질문 → {answer, sql} 반환."""
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        executed_sql: Optional[str] = None

        for _ in range(8):
            response = await self.client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=2048,
            )
            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # assistant 메시지를 대화 히스토리에 추가
            assistant_entry: dict = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_entry)

            # 툴 호출 없으면 최종 답변
            if finish_reason == "stop" or not msg.tool_calls:
                answer = msg.content or "응답 생성에 실패했습니다."
                break

            # 각 툴 실행 후 결과를 messages에 추가
            for tc in msg.tool_calls:
                args = json.loads(tc.function.arguments)
                if tc.function.name == "execute_query":
                    executed_sql = args.get("query")
                result = await self._call_tool(tc.function.name, args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                })
        else:
            answer = "응답 생성에 실패했습니다."

        return {"answer": answer, "sql": executed_sql}
