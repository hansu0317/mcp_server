"""
base.py — 백엔드 추상 인터페이스

【역할】
모든 데이터 백엔드(PostgreSQL, Dataverse, Snowflake 등)가
반드시 구현해야 하는 메서드를 정의한다.
server.py는 이 인터페이스만 바라보므로,
백엔드를 교체해도 MCP 툴 로직은 변경이 없다.

【확장 방법】
1. BaseBackend 상속
2. 아래 메서드 전부 구현
3. server.py의 get_backend()에 분기 추가
"""
from abc import ABC, abstractmethod


class BaseBackend(ABC):

    @abstractmethod
    async def list_tables(self) -> list[str]:
        """사용 가능한 테이블(엔티티) 목록 반환."""

    @abstractmethod
    async def get_table_schema(self, table_name: str) -> dict:
        """컬럼명·타입·외래키 정보 반환."""

    @abstractmethod
    async def execute_query(self, query: str) -> dict:
        """읽기 전용 쿼리 실행 후 {row_count, rows} 반환."""

    @abstractmethod
    async def get_sample_rows(self, table_name: str, limit: int) -> list:
        """샘플 데이터 N행 반환."""
