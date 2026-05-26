"""
query.py — POST /query 엔드포인트

자연어 질문을 받아 TextToSQL 서비스로 처리 후 결과 반환.
API Key 인증 필수.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import Tenant, verify_api_key
from api.services.text_to_sql import TextToSQLService

router = APIRouter(prefix="/query", tags=["query"])
_service: TextToSQLService | None = None


def get_service() -> TextToSQLService:
    global _service
    if _service is None:
        _service = TextToSQLService()
    return _service


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    sql: str | None = None


@router.post("", response_model=QueryResponse)
async def query(
    body: QueryRequest,
    tenant: Tenant = Depends(verify_api_key),
):
    result = await get_service().query(body.question)
    return QueryResponse(question=body.question, **result)
