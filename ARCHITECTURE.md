# CRM Text-to-SQL 아키텍처 문서

## 1. 전체 흐름 개요

사용자가 자연어로 질문하면, Claude가 MCP 툴을 통해 DB 구조를 파악하고 SQL을 생성·실행하여 결과를 반환한다.

```
사용자
  │
  │  "이번 달 성사된 딜의 총 금액은?"
  ▼
┌─────────────────────┐
│   FastAPI Server    │  :8000
│  POST /query        │
└────────┬────────────┘
         │
         │  1. 질문 전달
         ▼
┌─────────────────────────────────────────────────────┐
│              TextToSQL Service                      │
│                                                     │
│  - 시스템 프롬프트 구성 (CRM 전문가 역할 부여)         │
│  - Claude API 호출 (tool_use 모드)                  │
│  - MCP 툴 결과 → Claude에게 피드백                  │
│  - 최종 SQL + 결과 정리                             │
└────────┬──────────────────┬──────────────────────┘
         │                  │
         │ Anthropic SDK    │ subprocess (stdio)
         ▼                  ▼
┌──────────────┐   ┌────────────────────────┐
│  Claude API  │   │     MCP Server         │
│  (claude-    │   │   mcp_server/server.py │
│  sonnet-4-6) │   │                        │
│              │   │  툴 목록:              │
│  tool_use    │   │  - list_crm_tables     │
│  응답으로    │◄──│  - get_table_schema    │
│  어떤 툴을   │   │  - execute_sql         │
│  쓸지 결정   │   │  - get_sample_rows     │
└──────────────┘   └──────────┬─────────────┘
                              │
                              │ asyncpg
                              ▼
                   ┌────────────────────┐
                   │   PostgreSQL DB    │
                   │   (Docker :5432)   │
                   │                   │
                   │  customers        │
                   │  contacts         │
                   │  deals            │
                   │  products         │
                   │  deal_products    │
                   │  activities       │
                   └────────────────────┘
```

---

## 2. 컴포넌트별 역할

### 2-1. FastAPI Server (`api/`)
- 사용자와의 유일한 접점 (REST API)
- 요청을 받아 TextToSQL 서비스에 위임
- 응답 형식: `{ sql, result_rows, explanation }`

### 2-2. TextToSQL Service (`api/services/text_to_sql.py`)
- 실질적인 오케스트레이터
- Claude API를 `tool_use` 모드로 호출
- Claude가 툴 사용을 요청하면 → MCP Client에 전달 → 결과를 Claude에게 다시 전달
- 이 루프를 Claude가 최종 답변을 낼 때까지 반복

### 2-3. MCP Server (`mcp_server/server.py`)
- **별도 프로세스**로 실행 (stdio transport)
- PostgreSQL에 직접 연결하여 툴 4개를 노출
- SELECT만 허용 (DML/DDL 차단)

### 2-4. MCP Client (`api/services/mcp_client.py`)
- FastAPI 시작 시 MCP Server 프로세스를 subprocess로 띄움
- Claude가 `tool_use`로 툴을 요청하면 → MCP Server에 전달 → 결과 반환

---

## 3. Claude의 Tool Use 루프 상세

```
[1단계] FastAPI → Claude API 첫 호출
        메시지: "이번 달 성사된 딜의 총 금액은?"
        + 시스템 프롬프트: "당신은 CRM DB 전문가. 아래 툴로 DB를 조회하세요."
        + 툴 정의 4개 첨부

[2단계] Claude 응답: tool_use
        → "list_crm_tables 를 먼저 호출해서 테이블 파악"

[3단계] Service → MCP Server → list_crm_tables 실행
        결과: { customers, contacts, deals, ... } 테이블 설명

[4단계] 결과를 tool_result 로 Claude에 재전달

[5단계] Claude 응답: tool_use
        → "deals 테이블 스키마가 필요함 → get_table_schema(deals)"

[6단계] Service → MCP Server → get_table_schema("deals") 실행
        결과: 컬럼 목록 (stage, amount, closed_at, ...)

[7단계] 결과를 tool_result 로 Claude에 재전달

[8단계] Claude 응답: tool_use
        → SQL 생성 후 execute_sql 호출
        SQL: SELECT SUM(amount) FROM deals
             WHERE stage='closed_won'
             AND closed_at >= DATE_TRUNC('month', NOW())

[9단계] Service → MCP Server → execute_sql 실행
        결과: [{ "sum": 216000000 }]

[10단계] 결과를 tool_result 로 Claude에 재전달

[11단계] Claude 최종 응답 (text)
         "이번 달 성사된 딜의 총 금액은 216,000,000원입니다."
```

---

## 4. 디렉터리 구조

```
crm-text-to-sql/
│
├── CLAUDE.md               ← Claude Code 지침
├── ARCHITECTURE.md         ← 이 문서
├── docker-compose.yml      ← PostgreSQL 컨테이너
├── .env.example            ← 환경변수 템플릿
├── requirements.txt
│
├── mcp_server/
│   ├── server.py           ← MCP 서버 본체 (stdio, 4개 툴)
│   └── database.py         ← asyncpg 연결 풀
│
├── api/
│   ├── main.py             ← FastAPI 앱, 라이프사이클 관리
│   ├── routes/
│   │   ├── query.py        ← POST /query
│   │   └── schema.py       ← GET  /schema/{table}
│   ├── services/
│   │   ├── text_to_sql.py  ← Claude API 오케스트레이터
│   │   └── mcp_client.py   ← MCP subprocess 클라이언트
│   └── models/
│       └── schemas.py      ← Pydantic 모델
│
└── scripts/
    ├── init_db.sql         ← 테이블 DDL
    └── seed_data.py        ← 샘플 CRM 데이터
```

---

## 5. MCP 툴 명세

| 툴 이름 | 입력 | 출력 | 목적 |
|---------|------|------|------|
| `list_crm_tables` | 없음 | 테이블명 + 한 줄 설명 | 어떤 테이블이 있는지 파악 |
| `get_table_schema` | `table_name` | 컬럼/타입/FK 목록 | SQL 작성 전 스키마 확인 |
| `execute_sql` | `sql` (SELECT만) | rows + row_count | 실제 데이터 조회 |
| `get_sample_rows` | `table_name`, `limit` | N행 샘플 | 데이터 형태 파악 |

---

## 6. CRM 데이터 모델 (ERD 요약)

```
customers (1) ──── (N) contacts
    │
    └── (1) ──── (N) deals ──── (N) deal_products ──── (N) products
                      │
                      └── (1) ──── (N) activities
```

| 테이블 | 핵심 컬럼 |
|--------|-----------|
| customers | name, industry, annual_revenue, employee_count |
| contacts | customer_id(FK), name, email, position, is_primary |
| deals | customer_id(FK), owner, **stage**, **amount**, closed_at |
| products | name, category, unit_price |
| deal_products | deal_id(FK), product_id(FK), quantity, unit_price |
| activities | deal_id(FK), **type**(call/email/meeting/note), occurred_at |

`deals.stage` 값: `prospecting → qualification → proposal → negotiation → closed_won / closed_lost`

---

## 7. 보안 설계

- **읽기 전용 강제**: MCP Server의 `execute_sql` 툴에서 정규식으로 DML/DDL 차단
- **행 수 제한**: LIMIT 미지정 시 자동으로 MAX_QUERY_ROWS(기본 100) 추가
- **DB 권한**: PostgreSQL 사용자에 SELECT 권한만 부여 권장
- **API Key**: 환경변수로만 관리, 코드에 하드코딩 금지

---

## 8. 기술 스택 요약

| 항목 | 현재 (데모) | 향후 (프로덕션) |
|------|------------|----------------|
| 언어 | Python 3.9+ | Python 3.9+ |
| API 프레임워크 | FastAPI | FastAPI |
| LLM | Groq (llama-3.3-70b) / Claude (테스트용) | Claude claude-sonnet-4-6 |
| MCP | `mcp` Python SDK, stdio transport | stdio transport 유지 |
| DB 드라이버 | asyncpg (비동기) | Microsoft Dataverse REST API |
| DB | PostgreSQL 15 (Docker) | **MS Dynamics 365 Dataverse** |
| 환경변수 | python-dotenv | Azure Key Vault 연동 |

---

## 9. MS Dynamics 365 / Dataverse 전환 계획

현재 데모는 PostgreSQL로 동작하지만, DB 백엔드를 교체 가능하도록 추상화되어 있다.

```
mcp_server/backends/
├── base.py          ← 추상 인터페이스 (list_tables, get_schema, execute_query)
├── postgres.py      ← 현재 사용 중 (asyncpg + PostgreSQL)
└── dataverse.py     ← 향후 구현 (MS Dataverse REST API / OData)
```

**Dataverse 전환 시 변경 포인트:**
- `DATABASE_URL` → `DATAVERSE_URL` + `AZURE_CLIENT_ID/SECRET/TENANT_ID`
- `execute_sql` 툴 → `execute_odata` 툴 (FetchXML 또는 OData 쿼리)
- LLM 프롬프트에 Dataverse 테이블명(엔티티명) 주입
- MCP Server의 백엔드만 교체 — FastAPI/서비스 레이어 변경 없음

**MS365 연계 인증 흐름 (예정):**
```
FastAPI → Azure AD OAuth2 (app registration)
        → Dataverse Web API (OData v4)
        → Dynamics 365 엔티티 (account, contact, opportunity 등)
```
