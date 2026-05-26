"""
dataverse.py — Microsoft Dataverse 백엔드 (향후 구현)

환경변수 (예정):
  DATAVERSE_URL      = https://yourorg.crm.dynamics.com
  AZURE_CLIENT_ID    = ...
  AZURE_CLIENT_SECRET= ...
  AZURE_TENANT_ID    = ...
"""
from .base import BaseBackend


class DataverseBackend(BaseBackend):

    async def list_tables(self) -> list[str]:
        raise NotImplementedError("Dataverse 백엔드는 아직 구현되지 않았습니다.")

    async def get_table_schema(self, table_name: str) -> dict:
        raise NotImplementedError

    async def execute_query(self, query: str) -> dict:
        raise NotImplementedError

    async def get_sample_rows(self, table_name: str, limit: int) -> list:
        raise NotImplementedError
