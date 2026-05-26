"""
tenant.py — 테넌트(고객사) 모델

각 고객은 tenant_id + api_key + db 설정을 가진다.
"""
from dataclasses import dataclass


@dataclass
class Tenant:
    tenant_id: str    # 고객 식별자 (예: "customer-a")
    api_key: str      # 인증 키 (Bearer 토큰)
    db_backend: str   # postgres | dataverse | snowflake
    db_config: dict   # 백엔드별 연결 정보
