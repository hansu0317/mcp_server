# PaaS 아키텍처 설계서

## 1. 제품 비전

고객이 자신의 데이터 소스(PostgreSQL, Dataverse, Snowflake 등)를 연결하면,
Claude를 통해 자연어로 데이터를 조회할 수 있는 AI 데이터 플랫폼.

---

## 2. 전체 아키텍처

```
【고객 A — Claude Desktop/Code 사용자】
         │
         │ MCP over HTTP/SSE
         ▼
┌────────────────────────────────────────────────┐
│              우리 PaaS 플랫폼                   │
│                                                │
│  ┌──────────────────────────────────────────┐  │
│  │              FastAPI                     │  │
│  │  POST /query     ← TextToSQL REST API    │  │
│  │  GET  /mcp/sse   ← MCP over SSE          │  │
│  │  POST /auth/key  ← API Key 발급/검증      │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                              │
│  ┌──────────────▼───────────────────────────┐  │
│  │           MCP Server                     │  │
│  │  list_tables / get_table_schema          │  │
│  │  execute_query / get_sample_rows         │  │
│  │  web_search                              │  │
│  └──────────────┬───────────────────────────┘  │
│                 │                              │
│  ┌──────────────▼───────────────────────────┐  │
│  │         Backend Router (멀티테넌트)       │  │
│  │  tenant_id → 해당 고객의 DB 연결          │  │
│  └──────┬──────────┬──────────┬─────────────┘  │
│         │          │          │                │
│   PostgreSQL   Dataverse   Snowflake           │
│   (고객 A)     (고객 B)    (고객 C)             │
└────────────────────────────────────────────────┘
         ▲
         │ REST API
【고객 B — 웹앱 / 자체 시스템 연동】
```

---

## 3. 구현 단계 (로드맵)

### Phase 1 — SSE Transport (`feature/sse-transport`)
stdio(로컬 subprocess) → HTTP/SSE(원격 접속)로 전환.
고객이 네트워크로 MCP 서버에 연결 가능해진다.

```
변경 전: Claude Desktop → subprocess → server.py
변경 후: Claude Desktop → HTTP/SSE   → server.py
```

**파일:**
- `mcp_server/transport/stdio.py`  — 기존 stdio 유지 (로컬 개발용)
- `mcp_server/transport/sse.py`    — 신규 HTTP/SSE 구현

---

### Phase 2 — API Key 인증 (`feature/auth`)
고객별 API Key 발급 및 요청 검증.

```
요청 헤더: Authorization: Bearer <API_KEY>
          X-Tenant-ID: <tenant_id>
```

**파일:**
- `api/auth.py`  — API Key 검증 미들웨어
- `api/models/tenant.py`  — 테넌트 모델

---

### Phase 3 — FastAPI + TextToSQL (`feature/fastapi-textsql`)
자연어 질문 → Claude → MCP 툴 → SQL 실행 → 결과 반환.

```
POST /query
{
  "question": "이번 달 성사된 딜의 총 금액은?",
  "tenant_id": "customer-a"
}
→ { "answer": "...", "sql": "SELECT ...", "rows": [...] }
```

**파일:**
- `api/main.py`
- `api/routes/query.py`
- `api/services/text_to_sql.py`

---

### Phase 4 — 멀티테넌트 (`feature/multitenant`)
고객별로 다른 DB에 연결.
`tenant_id`로 해당 고객의 backend를 동적으로 선택.

```
tenant_id=customer-a → PostgreSQL (conn_str_A)
tenant_id=customer-b → Dataverse (env_B)
tenant_id=customer-c → Snowflake (conn_str_C)
```

**파일:**
- `api/services/tenant_registry.py`  — 테넌트별 backend 관리

---

## 4. 디렉터리 구조 (완성 시)

```
mcp_server/                     ← MCP 서버 코어
├── server.py                   ← 진입점
├── backends/
│   ├── base.py                 ← 추상 인터페이스 ✅
│   ├── postgres.py             ← PostgreSQL ✅
│   ├── dataverse.py            ← Dataverse (stub) ✅
│   └── snowflake.py            ← Snowflake (향후)
└── transport/
    ├── stdio.py                ← 로컬 개발용
    └── sse.py                  ← PaaS용 HTTP/SSE

api/                            ← FastAPI PaaS 레이어
├── main.py
├── auth.py                     ← API Key 인증
├── routes/
│   ├── query.py                ← POST /query (TextToSQL)
│   └── mcp.py                  ← GET /mcp/sse
├── services/
│   ├── text_to_sql.py          ← Claude + MCP 오케스트레이터
│   └── tenant_registry.py      ← 테넌트별 backend 관리
└── models/
    ├── schemas.py
    └── tenant.py

docs/
└── PAAS_ARCHITECTURE.md        ← 이 문서 ✅
```

---

## 5. 기술 스택

| 레이어 | 기술 |
|--------|------|
| API | FastAPI |
| LLM | Claude claude-sonnet-4-6 (Anthropic SDK) |
| MCP Transport | stdio (로컬) / SSE (PaaS) |
| DB — PostgreSQL | asyncpg |
| DB — Dataverse | MSAL + OData REST API |
| DB — Snowflake | snowflake-connector-python |
| 웹검색 | Tavily API |
| 인증 | API Key (헤더 기반) |
| 배포 | Docker + docker-compose |

---

## 6. 환경변수 구조 (완성 시)

```env
# 공통
ANTHROPIC_API_KEY=sk-ant-...
TAVILY_API_KEY=tvly-...

# MCP Transport 선택
MCP_TRANSPORT=sse          # stdio | sse
MCP_PORT=8001              # SSE 포트

# 기본 DB Backend
DB_BACKEND=postgres        # postgres | dataverse | snowflake
DATABASE_URL=postgresql://...

# 테넌트 레지스트리 (JSON 또는 외부 설정)
TENANT_CONFIG_PATH=config/tenants.json
```
