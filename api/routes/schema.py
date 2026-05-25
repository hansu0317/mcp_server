from fastapi import APIRouter, HTTPException
from api.services.mcp_client import mcp_manager

router = APIRouter(prefix="/schema", tags=["schema"])


@router.get("/tables")
async def list_tables():
    result = await mcp_manager.call_tool("list_crm_tables", {})
    import json
    return json.loads(result)


@router.get("/{table_name}")
async def get_table_schema(table_name: str):
    result = await mcp_manager.call_tool("get_table_schema", {"table_name": table_name})
    import json
    try:
        return json.loads(result)
    except Exception:
        raise HTTPException(status_code=400, detail=result)
