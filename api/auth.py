"""
auth.py — API Key 인증 미들웨어

【흐름】
  HTTP 요청
    │  Authorization: Bearer <API_KEY>
    ▼
  verify_api_key()
    ├── 키 존재 확인
    ├── 테넌트 조회
    └── 요청 처리 허용 / 401 반환

【확장 포인트】
  현재는 메모리(TENANT_REGISTRY)에 테넌트를 저장.
  프로덕션에서는 DB나 외부 서비스로 교체.
"""
import os
from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from api.models.tenant import Tenant

_bearer = HTTPBearer()

# 메모리 테넌트 레지스트리 — 프로덕션에서는 DB로 교체
TENANT_REGISTRY: dict[str, Tenant] = {
    "demo-key-001": Tenant(
        tenant_id="demo",
        api_key="demo-key-001",
        db_backend="postgres",
        db_config={"database_url": os.environ.get("DATABASE_URL", "")},
    )
}


def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(_bearer),
) -> Tenant:
    """API Key 검증 후 테넌트 반환. 실패 시 401."""
    api_key = credentials.credentials
    tenant = TENANT_REGISTRY.get(api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="유효하지 않은 API Key입니다.")
    return tenant


def register_tenant(tenant: Tenant) -> None:
    """테넌트 등록 (관리자 API 또는 초기화 시 사용)."""
    TENANT_REGISTRY[tenant.api_key] = tenant
