# CRM Text-to-SQL (MCP Architecture)

## 프로젝트 개요

자연어(한국어/영어)로 CRM 데이터를 조회할 수 있는 Text-to-SQL 시스템.
MCP(Model Context Protocol) 서버가 PostgreSQL CRM DB 툴을 노출하고,
Claude API가 LLM으로서 자연어 → SQL 변환을 수행한다.

```
[User NL Query]
      │
      ▼
[FastAPI Server :8000]
      │
      ▼
[TextToSQL Service]  ──────►  [Claude API (claude-sonnet-4-6)]
      │                              │ tool_use
      ▼                              ▼
[MCP Client]  ◄──────────►  [MCP Server (stdio)]
                                     │
                                     ▼
                            [PostgreSQL CRM DB]
```

## 아키텍처

| 레이어 | 역할 | 기술 |
|--------|------|------|
| API 레이어 | REST 엔드포인트 | FastAPI |
| LLM 레이어 | 자연어→SQL 변환 | Claude claude-sonnet-4-6 via Anthropic SDK |
| MCP 서버 | DB 툴 노출 (schema, query 실행) | `mcp` Python SDK (stdio transport) |
| DB 레이어 | CRM 데이터 저장 | PostgreSQL 15 |

## CRM 스키마

```
customers       - 고객사 (회사)
contacts        - 담당자 (개인)
deals           - 영업 기회
activities      - 활동 이력 (call, email, meeting)
products        - 제품/서비스
deal_products   - 딜-제품 연결
```

## 디렉터리 구조

```
crm-text-to-sql/
├── CLAUDE.md
├── docker-compose.yml          # PostgreSQL 컨테이너
├── .env.example
├── requirements.txt
├── mcp_server/
│   ├── server.py               # MCP 서버 (stdio) — DB 툴 정의
│   └── database.py             # asyncpg 연결 풀
├── api/
│   ├── main.py                 # FastAPI 앱 진입점
│   ├── routes/
│   │   ├── query.py            # POST /query  (text→sql→result)
│   │   └── schema.py           # GET  /schema (테이블 목록/구조)
│   ├── services/
│   │   ├── text_to_sql.py      # Claude API + MCP 통합 서비스
│   │   └── mcp_client.py       # MCP 서버 subprocess 관리
│   └── models/
│       └── schemas.py          # Pydantic 요청/응답 모델
└── scripts/
    ├── init_db.sql             # CRM 스키마 + 시드 데이터
    └── seed_data.py            # 샘플 CRM 데이터 삽입
```

## 환경 변수 (.env)

```
DATABASE_URL=postgresql://crm_user:crm_pass@localhost:5432/crm_db
ANTHROPIC_API_KEY=sk-ant-...
MCP_SERVER_PATH=mcp_server/server.py
```

## 실행 방법

```bash
# 1. PostgreSQL 시작
docker compose up -d postgres

# 2. DB 초기화
psql $DATABASE_URL -f scripts/init_db.sql
python3 scripts/seed_data.py

# 3. 의존성 설치
pip install -r requirements.txt

# 4. API 서버 시작
uvicorn api.main:app --reload --port 8000

# 5. 쿼리 테스트
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "이번 달 성사된 딜의 총 금액은?"}'
```

## MCP 툴 목록

| 툴 이름 | 설명 |
|---------|------|
| `list_crm_tables` | 사용 가능한 CRM 테이블 목록 반환 |
| `get_table_schema` | 특정 테이블의 컬럼/타입/관계 반환 |
| `execute_sql` | SELECT 쿼리 실행 후 결과 반환 (DML 차단) |
| `get_sample_rows` | 테이블의 샘플 데이터 N행 반환 |

## 개발 규칙

- `execute_sql` 툴은 **SELECT만** 허용. INSERT/UPDATE/DELETE/DROP 차단.
- 모든 SQL은 Claude가 생성 후 MCP를 통해 실행. API 레이어는 SQL을 직접 실행하지 않는다.
- 에러 시 Claude가 스키마를 다시 확인하고 SQL을 수정하는 **retry 루프** 1회 허용.
- Claude 모델: `claude-sonnet-4-6` (최신 Sonnet, prompt caching 활성화)
- MCP transport: **stdio** (subprocess, 별도 네트워크 포트 불필요)
