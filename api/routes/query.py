"""
query.py — POST /query 엔드포인트

자연어 질문을 받아 TextToSQL 서비스로 처리 후 결과 반환.
API Key 인증 → 테넌트 조회 → 해당 고객의 DB backend 사용.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.auth import Tenant, verify_api_key
from api.services.tenant_registry import get_backend_for_tenant
from api.services.text_to_sql import TextToSQLService

router = APIRouter(prefix="/query", tags=["query"])


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
    # 테넌트별 backend로 서비스 생성 → 각 고객의 DB에 연결
    backend = get_backend_for_tenant(tenant)
    service = TextToSQLService(backend=backend)
    result = await service.query(body.question)
    return QueryResponse(question=body.question, **result)
