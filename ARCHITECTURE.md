# Architecture — CRM MCP Server

## 1. 전체 흐름

```
사용자 (자연어 질문)
    │
    ▼
Claude Desktop
    │  MCP 프로토콜 (JSON-RPC 2.0 / stdio)
    │  subprocess: python3 mcp_server/server.py
    ▼
┌─────────────────────────────────────────────┐
│  MCP Server  (mcp_server/server.py)         │
│                                             │
│  ┌─────────────────┐  ┌──────────────────┐  │
│  │  CRM DB 툴       │  │  웹검색 툴        │  │
│  │  list_tables    │  │  web_search      │  │
│  │  get_schema     │  │  (Tavily API)    │  │
│  │  execute_sql    │  └──────────────────┘  │
│  │  get_sample     │                        │
│  └────────┬────────┘                        │
└───────────┼─────────────────────────────────┘
            │  asyncpg
            ▼
    PostgreSQL (Docker)
    crm_db / public 스키마
```

## 2. 컴포넌트 상세

### MCP Server (`mcp_server/server.py`)
- **transport**: stdio — Claude Desktop이 subprocess로 직접 실행
- **프로토콜**: JSON-RPC 2.0 직접 구현 (외부 mcp SDK 미사용)
- **테이블 목록**: `information_schema`에서 동적 조회 (하드코딩 없음)
- **보안**: `execute_sql`은 정규식으로 DML/DDL 차단 (SELECT만 허용)

### Database (`mcp_server/database.py`)
- asyncpg 연결 풀 (모듈 레벨 싱글턴)
- `DATABASE_URL` 환경 변수로 접속 정보 주입

### Claude Desktop 연결 설정

```json
// ~/Library/Application Support/Claude/claude_desktop_config.json
{
  "mcpServers": {
    "crm-server": {
      "command": "python3",
      "args": ["/절대경로/mcp_server/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://crm_user:crm_pass@localhost:5432/crm_db",
        "TAVILY_API_KEY": "tvly-your-key-here"
      }
    }
  }
}
```

## 3. MCP 툴 명세

| 툴 | 입력 | 출력 | 목적 |
|----|------|------|------|
| `list_crm_tables` | 없음 | 테이블명 + 컬럼 요약 | 사용 가능한 테이블 파악 |
| `get_table_schema` | `table_name` | 컬럼·타입·FK 목록 | SQL 작성 전 스키마 확인 |
| `execute_sql` | `sql` (SELECT만) | rows + row_count | 실제 데이터 조회 |
| `get_sample_rows` | `table_name`, `limit` | N행 샘플 | 데이터 형태 파악 |
| `web_search` | `query`, `max_results` | 검색 결과 리스트 | 외부 정보 검색 |

## 4. CRM 데이터 모델 (ERD)

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

`deals.stage`: `prospecting → qualification → proposal → negotiation → closed_won / closed_lost`

## 5. 보안 설계

- **읽기 전용**: `execute_sql`에서 정규식으로 DML/DDL 키워드 차단
- **행 수 제한**: LIMIT 미지정 시 `MAX_QUERY_ROWS`(기본 100) 자동 추가
- **API Key**: 환경변수로만 관리 — 코드 및 git에 하드코딩 금지

## 6. 브랜치 전략

```
main  ← 안정 버전 (배포 기준)
  └── feature/web-search-tool   ← Tavily 웹검색 구현
  └── feature/chatbot-ui        ← 향후 독립 UI 필요 시
```
