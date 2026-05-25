"""
Text-to-SQL 오케스트레이터

LLM(Groq 또는 Claude)이 MCP 툴을 통해 DB 스키마를 파악하고 SQL을 생성·실행한다.

LLM 전환 방법 (.env):
  LLM_PROVIDER=groq   → Groq llama-3.3-70b (현재)
  LLM_PROVIDER=claude → Claude claude-sonnet-4-6 (최종 테스트용)
"""
import json
import os
import re
from typing import Optional, List, Tuple

# ── Groq (현재 사용) ──────────────────────────────────────────────────────────
from groq import AsyncGroq

# ── Claude API (최종 테스트 시 주석 해제, LLM_PROVIDER=claude 설정) ──────────
# import anthropic
# ─────────────────────────────────────────────────────────────────────────────

from api.services.mcp_client import MCPClientManager
from api.models.schemas import QueryResponse

SYSTEM_PROMPT = """당신은 CRM 데이터 분석 전문가입니다.
사용자의 자연어 질문을 받아 MCP 툴을 사용해 DB 스키마를 파악하고 SQL을 작성·실행하여 답변합니다.

규칙:
1. 반드시 get_table_schema 툴로 스키마를 확인한 후 SQL을 작성하세요.
2. execute_sql 툴로 SQL을 실행하고 결과를 기반으로 답변하세요.
3. SQL 오류 발생 시 스키마를 다시 확인하고 1회 재시도하세요.
4. 금액은 한국 원화(원) 단위로 표시하고 천 단위 구분자를 사용하세요.
5. 답변은 한국어로 작성하세요.
6. 실행한 SQL을 답변에 포함시키세요.
"""


def _build_groq_client() -> AsyncGroq:
    return AsyncGroq(api_key=os.environ["GROQ_API_KEY"])


# def _build_claude_client():
#     return anthropic.AsyncAnthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _extract_sql_and_rows(messages: List[dict]) -> Tuple[Optional[str], Optional[List], int]:
    """대화 이력에서 실행된 SQL과 결과 행을 추출한다."""
    sql = None
    rows = None
    row_count = 0

    for msg in messages:
        # tool call 에서 SQL 추출
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                if tc["function"]["name"] == "execute_sql":
                    try:
                        args = json.loads(tc["function"]["arguments"])
                        sql = args.get("sql")
                    except Exception:
                        pass

        # tool result 에서 행 추출
        if msg.get("role") == "tool":
            try:
                data = json.loads(msg["content"])
                if isinstance(data, dict) and "rows" in data:
                    rows = data["rows"]
                    row_count = data.get("row_count", len(rows))
            except Exception:
                pass

    return sql, rows, row_count


class TextToSQLService:
    def __init__(self, mcp: MCPClientManager):
        self.mcp = mcp
        self.provider = os.environ.get("LLM_PROVIDER", "groq").lower()

        if self.provider == "groq":
            self.groq = _build_groq_client()
            self.model = "llama-3.3-70b-versatile"
        # elif self.provider == "claude":
        #     self.claude = _build_claude_client()
        #     self.model = "claude-sonnet-4-6"
        else:
            raise ValueError(f"지원하지 않는 LLM_PROVIDER: {self.provider}")

    async def query(self, question: str) -> QueryResponse:
        if self.provider == "groq":
            return await self._query_groq(question)
        # elif self.provider == "claude":
        #     return await self._query_claude(question)

    # ── Groq Tool-Use 루프 ────────────────────────────────────────────────────

    async def _query_groq(self, question: str) -> QueryResponse:
        tools = self.mcp.tools_as_openai_format()
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        max_iterations = 8  # 무한 루프 방지
        for _ in range(max_iterations):
            response = await self.groq.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                max_tokens=2048,
            )

            msg = response.choices[0].message
            finish_reason = response.choices[0].finish_reason

            # assistant 메시지 이력에 추가
            assistant_entry = {"role": "assistant", "content": msg.content or ""}
            if msg.tool_calls:
                assistant_entry["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_entry)

            # 최종 답변
            if finish_reason == "stop" or not msg.tool_calls:
                sql, rows, row_count = _extract_sql_and_rows(messages)
                return QueryResponse(
                    question=question,
                    sql=sql,
                    explanation=msg.content or "",
                    rows=rows,
                    row_count=row_count,
                    llm_provider="groq",
                )

            # 툴 호출 처리
            for tc in msg.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    tool_args = {}

                result_text = await self.mcp.call_tool(tool_name, tool_args)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                })

        # max_iterations 초과 시 마지막 assistant 메시지 반환
        sql, rows, row_count = _extract_sql_and_rows(messages)
        last_content = next(
            (m["content"] for m in reversed(messages) if m.get("role") == "assistant"),
            "응답을 생성하지 못했습니다.",
        )
        return QueryResponse(
            question=question,
            sql=sql,
            explanation=last_content,
            rows=rows,
            row_count=row_count,
            llm_provider="groq",
        )

    # ── Claude Tool-Use 루프 (최종 테스트용 — 주석 해제하여 사용) ────────────
    #
    # async def _query_claude(self, question: str) -> QueryResponse:
    #     mcp_tools = self.mcp.get_tools()
    #     claude_tools = [
    #         {
    #             "name": t.name,
    #             "description": t.description or "",
    #             "input_schema": t.inputSchema,
    #         }
    #         for t in mcp_tools
    #     ]
    #     messages = [{"role": "user", "content": question}]
    #
    #     for _ in range(8):
    #         response = await self.claude.messages.create(
    #             model=self.model,
    #             max_tokens=2048,
    #             system=SYSTEM_PROMPT,
    #             tools=claude_tools,
    #             messages=messages,
    #         )
    #         messages.append({"role": "assistant", "content": response.content})
    #
    #         if response.stop_reason == "end_turn":
    #             text = next((b.text for b in response.content if hasattr(b, "text")), "")
    #             sql, rows, row_count = _extract_sql_and_rows_claude(messages)
    #             return QueryResponse(
    #                 question=question, sql=sql, explanation=text,
    #                 rows=rows, row_count=row_count, llm_provider="claude",
    #             )
    #
    #         tool_results = []
    #         for block in response.content:
    #             if block.type == "tool_use":
    #                 result_text = await self.mcp.call_tool(block.name, block.input)
    #                 tool_results.append({
    #                     "type": "tool_result",
    #                     "tool_use_id": block.id,
    #                     "content": result_text,
    #                 })
    #         messages.append({"role": "user", "content": tool_results})
    #
    #     return QueryResponse(question=question, explanation="응답 생성 실패", llm_provider="claude")
