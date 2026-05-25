from fastapi import APIRouter, Depends, HTTPException
from api.models.schemas import QueryRequest, QueryResponse
from api.services.text_to_sql import TextToSQLService
from api.services.mcp_client import mcp_manager

router = APIRouter(prefix="/query", tags=["query"])


def get_service() -> TextToSQLService:
    return TextToSQLService(mcp=mcp_manager)


@router.post("", response_model=QueryResponse)
async def text_to_sql(request: QueryRequest, svc: TextToSQLService = Depends(get_service)):
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="question이 비어 있습니다.")
    return await svc.query(request.question)
