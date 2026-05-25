-- CRM Database Schema

CREATE TABLE IF NOT EXISTS customers (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    industry    VARCHAR(100),
    country     VARCHAR(100) DEFAULT '대한민국',
    annual_revenue BIGINT,
    employee_count INT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS contacts (
    id          SERIAL PRIMARY KEY,
    customer_id INT REFERENCES customers(id) ON DELETE CASCADE,
    name        VARCHAR(100) NOT NULL,
    email       VARCHAR(200) UNIQUE,
    phone       VARCHAR(50),
    position    VARCHAR(100),
    is_primary  BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS products (
    id          SERIAL PRIMARY KEY,
    name        VARCHAR(200) NOT NULL,
    category    VARCHAR(100),
    unit_price  BIGINT NOT NULL,
    description TEXT
);

CREATE TABLE IF NOT EXISTS deals (
    id          SERIAL PRIMARY KEY,
    title       VARCHAR(300) NOT NULL,
    customer_id INT REFERENCES customers(id),
    contact_id  INT REFERENCES contacts(id),
    owner       VARCHAR(100),
    stage       VARCHAR(50) CHECK (stage IN ('prospecting','qualification','proposal','negotiation','closed_won','closed_lost')),
    amount      BIGINT,
    probability INT CHECK (probability BETWEEN 0 AND 100),
    expected_close_date DATE,
    closed_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS deal_products (
    id          SERIAL PRIMARY KEY,
    deal_id     INT REFERENCES deals(id) ON DELETE CASCADE,
    product_id  INT REFERENCES products(id),
    quantity    INT DEFAULT 1,
    unit_price  BIGINT
);

CREATE TABLE IF NOT EXISTS activities (
    id          SERIAL PRIMARY KEY,
    deal_id     INT REFERENCES deals(id) ON DELETE CASCADE,
    contact_id  INT REFERENCES contacts(id),
    type        VARCHAR(50) CHECK (type IN ('call','email','meeting','note')),
    subject     VARCHAR(300),
    body        TEXT,
    occurred_at TIMESTAMPTZ DEFAULT NOW(),
    created_by  VARCHAR(100)
);

-- 분석용 인덱스
CREATE INDEX ON deals(stage);
CREATE INDEX ON deals(owner);
CREATE INDEX ON deals(customer_id);
CREATE INDEX ON deals(created_at);
CREATE INDEX ON activities(deal_id);
CREATE INDEX ON activities(type);
CREATE INDEX ON activities(occurred_at);
