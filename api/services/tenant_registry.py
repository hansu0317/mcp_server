"""
tenant_registry.py — 테넌트별 backend 관리

【흐름】
  API Key → Tenant 조회 → 해당 고객의 PostgresBackend 반환

각 고객은 자신의 DATABASE_URL을 가진다.
같은 PostgresBackend 코드가 다른 DB에 연결된다.
"""
import os
from functools import lru_cache

from api.auth import TENANT_REGISTRY, register_tenant, Tenant
from mcp_server.backends.postgres import PostgresBackend


# 테넌트별 backend 인스턴스 캐시 (tenant_id → PostgresBackend)
_backend_cache: dict[str, PostgresBackend] = {}


def get_backend_for_tenant(tenant: Tenant) -> PostgresBackend:
    """테넌트 전용 PostgresBackend 반환 (인스턴스 재사용)."""
    if tenant.tenant_id not in _backend_cache:
        # 테넌트 DB URL을 환경변수로 주입해서 backend 생성
        os.environ["DATABASE_URL"] = tenant.db_config["database_url"]
        _backend_cache[tenant.tenant_id] = PostgresBackend()
    return _backend_cache[tenant.tenant_id]


def add_tenant(tenant_id: str, api_key: str, database_url: str) -> Tenant:
    """새 테넌트 등록 (관리자 API에서 사용)."""
    tenant = Tenant(
        tenant_id=tenant_id,
        api_key=api_key,
        db_backend="postgres",
        db_config={"database_url": database_url},
    )
    register_tenant(tenant)
    return tenant


# 기본 demo 테넌트 — .env의 DATABASE_URL 사용
_default_url = os.environ.get("DATABASE_URL", "")
if _default_url:
    add_tenant("demo", "demo-key-001", _default_url)
