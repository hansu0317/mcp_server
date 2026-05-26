# CRM MCP Server — 발표 자료

## 1. 무엇을 만들었나?

**자연어로 데이터를 조회하는 AI PaaS 플랫폼**

> "이번 달 성사된 딜의 총 금액은?"
> → Claude AI가 자동으로 SQL 생성 → DB 조회 → 한국어 답변

---

## 2. 핵심 기술 — MCP (Model Context Protocol)

```
기존 방식                      MCP 방식
──────────────────             ──────────────────────────
개발자가 SQL 작성              Claude가 SQL 자동 생성
API 엔드포인트 하드코딩         툴(Tool)을 플러그인처럼 연결
LLM과 DB 연동 직접 구현         MCP 표준 프로토콜로 자동 연결
```

**MCP = Claude가 외부 시스템을 도구처럼 쓸 수 있게 해주는 표준**

---

## 3. 전체 아키텍처

```
【Claude Desktop/Code 사용자】      【웹앱/API 사용자】
           │                               │
           │ MCP (stdio/SSE)               │ REST API
           ▼                               ▼
    ┌──────────────────────────────────────────────┐
    │              우리 PaaS 플랫폼                 │
    │                                              │
    │  FastAPI                                     │
    │  ├── POST /query  ← 자연어 → SQL → 결과       │
    │  ├── GET  /mcp/sse ← MCP over HTTP           │
    │  └── API Key 인증 (고객별)                    │
    │                                              │
    │  MCP Server (5개 툴)                         │
    │  ├── list_tables      DB 테이블 목록          │
    │  ├── get_table_schema 컬럼/타입/관계          │
    │  ├── execute_query    SELECT 실행 (DML 차단)  │
    │  ├── get_sample_rows  샘플 데이터             │
    │  └── web_search       Tavily 실시간 검색      │
    │                                              │
    │  Backend 추상화                              │
    │  └── PostgreSQL ← 현재                       │
    │      Dataverse  ← 향후 (플러그인)             │
    │      Snowflake  ← 향후 (플러그인)             │
    └──────────────────────────────────────────────┘
```

---

## 4. 오늘 구현한 것 (브랜치별)

| 브랜치 | 내용 |
|--------|------|
| `feature/web-search-tool` | Tavily 웹검색 MCP 툴 |
| `feature/backend-abstraction` | DB 교체 가능한 추상 레이어 |
| `feature/sse-transport` | stdio → HTTP/SSE 원격 연결 |
| `feature/auth` | API Key 인증 (고객별) |
| `feature/fastapi-textsql` | FastAPI + Claude TextToSQL |
| `feature/multitenant` | 고객별 DB 분리 연결 |

---

## 5. 실제 동작 흐름 (2가지 시나리오)

### 시나리오 A — Claude Desktop 사용자

```
1. 고객이 Claude Desktop에서 질문
   "우리 회사 이번 달 매출은?"

2. Claude가 MCP 툴 자동 호출
   → list_tables() → deals 테이블 확인
   → get_table_schema("deals") → 컬럼 파악
   → execute_query("SELECT SUM(amount)...") → 실행

3. Claude가 결과를 자연어로 정리
   "이번 달 성사된 딜의 총 매출은 2,400만원입니다."
```

### 시나리오 B — 웹앱/REST API 사용자

```
1. 고객 시스템이 API 호출
   POST /query
   Authorization: Bearer demo-key-001
   { "question": "이번 달 매출은?" }

2. 우리 서버가 Claude API 직접 호출
   → 동일한 MCP 툴 로직 실행

3. JSON으로 결과 반환
   {
     "answer": "이번 달 매출은 2,400만원입니다.",
     "sql": "SELECT SUM(amount) FROM deals WHERE..."
   }
```

---

## 6. 핵심 설계 원칙

**① 하드코딩 없음**
- 테이블 목록 → DB에서 동적 조회
- DB 종류 → 환경변수로 교체

**② 보안**
- SELECT만 허용, DML 정규식 차단
- API Key 인증 (고객별 분리)
- 실제 키는 .env / git 커밋 차단

**③ 확장성**
- DB 백엔드 교체: `DB_BACKEND=dataverse` 한 줄로
- Transport 교체: `MCP_TRANSPORT=sse` 한 줄로

---

## 7. 기술 스택

| 항목 | 기술 |
|------|------|
| MCP Server | Python 3.11, JSON-RPC 2.0 |
| API | FastAPI + uvicorn |
| LLM | Claude claude-sonnet-4-6 (Anthropic) |
| DB | PostgreSQL 15 (Docker) |
| 웹검색 | Tavily API |
| 버전관리 | Git + GitHub |

---

## 8. 다음 단계

1. **Dataverse 백엔드** 구현 (MS Dynamics 연동)
2. **관리자 대시보드** — 테넌트 등록/관리 UI
3. **Docker 배포** — 컨테이너화 및 클라우드 배포
4. **Claude Desktop 로컬 연결** 실제 테스트
