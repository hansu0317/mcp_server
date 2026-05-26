# MCP Server — CRM + 웹검색

## 프로젝트 개요

**Claude Desktop**이 이 MCP 서버에 연결해 CRM 데이터 조회와 실시간 웹 검색을 수행한다.
별도의 API 서버나 Claude API 키 없이, Claude Desktop의 MCP 설정만으로 동작한다.

```
【전체 흐름】

  사용자
    │  자연어 질문
    ▼
  Claude Desktop (Anthropic 제공 앱)
    │  MCP 프로토콜 (JSON-RPC 2.0 / stdio)
    ▼
  MCP Server  ←─── 이 프로젝트
    ├── list_crm_tables   ─┐
    ├── get_table_schema  ─┤──► PostgreSQL (Docker)
    ├── execute_sql       ─┤
    ├── get_sample_rows   ─┘
    └── web_search        ────► Tavily API (인터넷 검색)
```

## 아키텍처

| 구성 요소 | 역할 | 기술 |
|-----------|------|------|
| Claude Desktop | LLM + UI | Anthropic 제공 앱 (별도 설치) |
| MCP Server | DB·웹검색 툴 노출 | Python, JSON-RPC 2.0 over stdio |
| PostgreSQL | CRM 데이터 저장 | Docker (asyncpg 드라이버) |
| Tavily | 실시간 웹 검색 | Tavily API |

> **stdio transport**: Claude Desktop이 `python3 mcp_server/server.py`를 subprocess로 실행.
> 별도 네트워크 포트 불필요.

## MCP 툴 목록

| 툴 | 설명 |
|----|------|
| `list_crm_tables` | DB의 실제 테이블 목록 + 컬럼 요약 (동적 조회) |
| `get_table_schema` | 특정 테이블의 컬럼·타입·외래키 상세 정보 |
| `execute_sql` | SELECT 쿼리 실행 — DML(INSERT/UPDATE/DELETE 등) 차단 |
| `get_sample_rows` | 테이블 샘플 데이터 N행 반환 |
| `web_search` | Tavily 기반 실시간 웹 검색 |

## CRM 스키마

```
customers     — 고객사 (회사): 업종, 연매출, 임직원 수
contacts      — 담당자 (개인): 이메일, 직책, 주요 연락처 여부
deals         — 영업 기회: stage, 금액, 담당 영업사원
activities    — 활동 이력: type(call/email/meeting/note), 발생일시
products      — 제품/서비스: 카테고리, 단가
deal_products — 딜↔제품 연결 (다대다)
```

## 디렉터리 구조

```
mcp_server/               ← 프로젝트 루트 (GitHub repo)
├── CLAUDE.md             ← 이 파일 (Claude Code용 프로젝트 가이드)
├── ARCHITECTURE.md       ← 상세 아키텍처 문서
├── docker-compose.yml    ← PostgreSQL 컨테이너
├── .env.example          ← 환경 변수 템플릿 (키 값 없음)
├── .gitignore
├── requirements.txt
├── mcp_server/
│   ├── server.py         ← MCP 서버 진입점 (툴 정의 + 핸들러)
│   └── database.py       ← asyncpg 연결 풀
└── scripts/
    ├── init_db.sql       ← CRM 스키마 생성
    └── seed_data.py      ← 샘플 데이터 삽입
```

## 환경 변수 (.env)

```env
# PostgreSQL
DATABASE_URL=postgresql://crm_user:crm_pass@localhost:5432/crm_db

# 웹검색 (Tavily) — https://app.tavily.com 에서 발급
TAVILY_API_KEY=tvly-your-key-here

# MCP 서버 설정
MAX_QUERY_ROWS=100
```

> `.env`는 `.gitignore`에 포함됨 — 절대 커밋 금지.

## Claude Desktop 연결 설정

`claude_desktop_config.json` (Mac: `~/Library/Application Support/Claude/`)에 추가:

```json
{
  "mcpServers": {
    "crm-server": {
      "command": "python3",
      "args": ["/절대경로/mcp_server/server.py"],
      "env": {
        "DATABASE_URL": "postgresql://crm_user:crm_pass@localhost:5432/crm_db",
        "TAVILY_API_KEY": "tvly-your-key-here",
        "MAX_QUERY_ROWS": "100"
      }
    }
  }
}
```

## 로컬 실행 방법

```bash
# 1. PostgreSQL 시작
docker compose up -d postgres

# 2. DB 초기화 (최초 1회)
psql $DATABASE_URL -f scripts/init_db.sql
python3 scripts/seed_data.py

# 3. 의존성 설치
pip install -r requirements.txt

# 4. MCP 서버 단독 테스트 (stdin으로 JSON-RPC 직접 입력)
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' \
  | python3 mcp_server/server.py
```

## 개발 규칙

- `execute_sql`은 **SELECT만** 허용. DML은 정규식으로 차단.
- 테이블 목록은 `information_schema`에서 **동적으로 조회** — 하드코딩 금지.
- MCP transport: **stdio** (Claude Desktop이 subprocess로 실행).
- 브랜치 전략: `main` (안정) / `feature/*` (기능 개발)
