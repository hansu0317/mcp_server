"""
DB 작업
CRM 샘플 데이터 삽입 스크립트
"""
import asyncio
import os
import asyncpg
from dotenv import load_dotenv

load_dotenv()

CUSTOMERS = [
    ("삼성SDS", "IT서비스", "대한민국", 5_000_000_000, 10000),
    ("LG CNS", "IT서비스", "대한민국", 3_200_000_000, 8000),
    ("현대오토에버", "IT서비스", "대한민국", 2_100_000_000, 5000),
    ("카카오엔터프라이즈", "클라우드", "대한민국", 800_000_000, 1200),
    ("네이버클라우드", "클라우드", "대한민국", 1_200_000_000, 2000),
    ("SK C&C", "IT컨설팅", "대한민국", 1_800_000_000, 4000),
    ("롯데정보통신", "IT서비스", "대한민국", 900_000_000, 2500),
    ("CJ올리브네트웍스", "IT서비스", "대한민국", 700_000_000, 1800),
]

PRODUCTS = [
    ("CRM Pro", "SaaS", 12_000_000, "고객관계관리 플랫폼 연간 라이선스"),
    ("Data Analytics Suite", "Analytics", 24_000_000, "비즈니스 인텔리전스 및 분석 도구"),
    ("Cloud Security Pack", "Security", 8_000_000, "클라우드 보안 솔루션"),
    ("AI Chatbot Platform", "AI", 18_000_000, "기업용 AI 챗봇 구축 플랫폼"),
    ("DevOps Toolchain", "DevOps", 6_000_000, "CI/CD 및 개발 자동화 도구"),
]

OWNERS = ["김민준", "이서연", "박지호", "최수아", "정동현"]

STAGES = [
    ("prospecting", 0.1),
    ("qualification", 0.2),
    ("proposal", 0.4),
    ("negotiation", 0.7),
    ("closed_won", 1.0),
    ("closed_lost", 0.0),
]

DEALS = [
    ("삼성SDS CRM 도입", 0, 0, 0, "closed_won", 120_000_000, 100, "2026-01-15", "2026-01-15"),
    ("LG CNS 데이터분석 프로젝트", 1, 1, 1, "closed_won", 240_000_000, 100, "2026-02-28", "2026-02-28"),
    ("현대오토에버 보안 강화", 2, 2, 2, "negotiation", 80_000_000, 70, "2026-03-31", None),
    ("카카오엔터 AI 챗봇", 3, 3, 3, "proposal", 180_000_000, 40, "2026-04-15", None),
    ("네이버클라우드 DevOps", 4, 4, 4, "qualification", 60_000_000, 20, "2026-05-31", None),
    ("SK C&C CRM 확장", 5, 5, 0, "closed_won", 96_000_000, 100, "2026-03-10", "2026-03-10"),
    ("롯데정보통신 분석툴", 6, 6, 1, "prospecting", 48_000_000, 10, "2026-06-30", None),
    ("CJ올리브 AI 도입", 7, 7, 2, "closed_lost", 90_000_000, 0, "2026-02-15", "2026-02-20"),
    ("삼성SDS DevOps 추가", 0, 0, 3, "negotiation", 36_000_000, 75, "2026-04-30", None),
    ("LG CNS 보안 업그레이드", 1, 1, 4, "proposal", 64_000_000, 45, "2026-05-15", None),
]


async def seed():
    url = os.environ["DATABASE_URL"]
    conn = await asyncpg.connect(url)

    try:
        # customers
        customer_ids = []
        for name, industry, country, revenue, emp in CUSTOMERS:
            cid = await conn.fetchval(
                "INSERT INTO customers(name,industry,country,annual_revenue,employee_count) "
                "VALUES($1,$2,$3,$4,$5) ON CONFLICT DO NOTHING RETURNING id",
                name, industry, country, revenue, emp,
            )
            if cid is None:
                cid = await conn.fetchval("SELECT id FROM customers WHERE name=$1", name)
            customer_ids.append(cid)

        # contacts
        contact_ids = []
        positions = ["IT 팀장", "구매 담당자", "CTO", "IT 임원", "개발팀장", "기술 이사", "IT 매니저", "구매팀장"]
        for i, (cid, (cname, *_)) in enumerate(zip(customer_ids, CUSTOMERS)):
            contact_name = f"담당자_{cname[:3]}"
            eid = await conn.fetchval(
                "INSERT INTO contacts(customer_id,name,email,phone,position,is_primary) "
                "VALUES($1,$2,$3,$4,$5,TRUE) ON CONFLICT(email) DO NOTHING RETURNING id",
                cid, contact_name,
                f"contact{i}@{cname.replace(' ','')}.co.kr",
                f"010-{1000+i:04d}-{2000+i:04d}",
                positions[i % len(positions)],
            )
            if eid is None:
                eid = await conn.fetchval("SELECT id FROM contacts WHERE customer_id=$1 LIMIT 1", cid)
            contact_ids.append(eid)

        # products
        product_ids = []
        for pname, cat, price, desc in PRODUCTS:
            pid = await conn.fetchval(
                "INSERT INTO products(name,category,unit_price,description) "
                "VALUES($1,$2,$3,$4) ON CONFLICT DO NOTHING RETURNING id",
                pname, cat, price, desc,
            )
            if pid is None:
                pid = await conn.fetchval("SELECT id FROM products WHERE name=$1", pname)
            product_ids.append(pid)

        # deals
        deal_ids = []
        import datetime
        for title, ci, coi, oi, stage, amount, prob, exp_date, closed in DEALS:
            owner = OWNERS[oi % len(OWNERS)]
            closed_at = datetime.datetime.fromisoformat(closed) if closed else None
            did = await conn.fetchval(
                "INSERT INTO deals(title,customer_id,contact_id,owner,stage,amount,probability,"
                "expected_close_date,closed_at) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id",
                title, customer_ids[ci], contact_ids[coi], owner, stage,
                amount, prob, datetime.date.fromisoformat(exp_date), closed_at,
            )
            deal_ids.append(did)
            # deal_products
            pid = product_ids[oi % len(product_ids)]
            await conn.execute(
                "INSERT INTO deal_products(deal_id,product_id,quantity,unit_price) VALUES($1,$2,1,$3)",
                did, pid, amount,
            )

        # activities
        import datetime as dt
        activity_types = ["call", "email", "meeting", "note"]
        subjects = ["초기 미팅", "제안서 발송", "데모 진행", "가격 협상", "계약 검토"]
        for i, did in enumerate(deal_ids):
            for j in range(2):
                days_ago = (i * 3 + j * 7) % 60
                occurred = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago)
                await conn.execute(
                    "INSERT INTO activities(deal_id,contact_id,type,subject,occurred_at,created_by) "
                    "VALUES($1,$2,$3,$4,$5,$6)",
                    did, contact_ids[i % len(contact_ids)],
                    activity_types[(i + j) % len(activity_types)],
                    subjects[(i + j) % len(subjects)],
                    occurred,
                    OWNERS[(i + j) % len(OWNERS)],
                )

        print(f"✓ customers: {len(customer_ids)}")
        print(f"✓ contacts:  {len(contact_ids)}")
        print(f"✓ products:  {len(product_ids)}")
        print(f"✓ deals:     {len(deal_ids)}")
        print("샘플 데이터 삽입 완료.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(seed())
