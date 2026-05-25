from typing import Optional, List, Any
from pydantic import BaseModel


class QueryRequest(BaseModel):
    question: str
    max_rows: Optional[int] = 100


class QueryResponse(BaseModel):
    question: str
    sql: Optional[str] = None
    explanation: str
    rows: Optional[List[Any]] = None
    row_count: int = 0
    llm_provider: str = "groq"


class SchemaResponse(BaseModel):
    table: str
    columns: List[dict]
    foreign_keys: List[dict]


class TablesResponse(BaseModel):
    tables: dict
