-- 001: core enterprise entities
CREATE TABLE IF NOT EXISTS organizations (
    org_id          VARCHAR(16) PRIMARY KEY,
    name            TEXT NOT NULL,
    parent_org_id   VARCHAR(16) REFERENCES organizations(org_id),
    country         CHAR(2),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS regions (
    region_id   VARCHAR(8) PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    currency    CHAR(3) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS business_units (
    bu_id       VARCHAR(8) PRIMARY KEY,
    org_id      VARCHAR(16) NOT NULL REFERENCES organizations(org_id),
    name        TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS products (
    product_id  VARCHAR(8) PRIMARY KEY,
    bu_id       VARCHAR(8) NOT NULL REFERENCES business_units(bu_id),
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    unit_price  NUMERIC(14,2) NOT NULL CHECK (unit_price >= 0),
    unit_cost   NUMERIC(14,2) NOT NULL CHECK (unit_cost >= 0),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS customers (
    customer_id         VARCHAR(8) PRIMARY KEY,
    name                TEXT NOT NULL,
    region_id           VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    segment             TEXT NOT NULL CHECK (segment IN ('Enterprise', 'Mid-Market', 'SMB')),
    industry            TEXT NOT NULL,
    signup_date         DATE,
    satisfaction_score  NUMERIC(4,1) CHECK (satisfaction_score BETWEEN 1 AND 10),
    credit_limit        NUMERIC(14,2) CHECK (credit_limit >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id  VARCHAR(10) PRIMARY KEY,
    customer_id     VARCHAR(8) NOT NULL REFERENCES customers(customer_id),
    product_id      VARCHAR(8) NOT NULL REFERENCES products(product_id),
    region_id       VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    bu_id           VARCHAR(8) NOT NULL REFERENCES business_units(bu_id),
    txn_date        DATE NOT NULL,
    quantity        INTEGER NOT NULL CHECK (quantity > 0),
    unit_price      NUMERIC(14,2) NOT NULL CHECK (unit_price >= 0),
    discount_pct    NUMERIC(5,3) NOT NULL CHECK (discount_pct BETWEEN 0 AND 0.6),
    revenue         NUMERIC(16,2) NOT NULL CHECK (revenue >= 0),
    cost            NUMERIC(16,2) NOT NULL CHECK (cost >= 0),
    channel         TEXT NOT NULL CHECK (channel IN ('direct', 'partner', 'online')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS employees (
    employee_id         VARCHAR(8) PRIMARY KEY,
    bu_id               VARCHAR(8) NOT NULL REFERENCES business_units(bu_id),
    region_id           VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    role                TEXT NOT NULL,
    hire_date           DATE NOT NULL,
    annual_salary       NUMERIC(12,2) CHECK (annual_salary > 0),
    performance_rating  SMALLINT CHECK (performance_rating BETWEEN 1 AND 5),
    is_active           BOOLEAN NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id             VARCHAR(8) PRIMARY KEY,
    name                    TEXT NOT NULL,
    region_id               VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    category                TEXT NOT NULL,
    annual_spend            NUMERIC(16,2) CHECK (annual_spend >= 0),
    on_time_delivery_pct    NUMERIC(5,1) CHECK (on_time_delivery_pct BETWEEN 0 AND 100),
    quality_score           NUMERIC(4,1) CHECK (quality_score BETWEEN 0 AND 10),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS operations (
    operation_id        VARCHAR(10) PRIMARY KEY,
    op_date             DATE NOT NULL,
    region_id           VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    bu_id               VARCHAR(8) NOT NULL REFERENCES business_units(bu_id),
    headcount           NUMERIC(10,1) CHECK (headcount >= 0),
    orders_processed    INTEGER CHECK (orders_processed >= 0),
    fulfillment_hours   NUMERIC(10,2),
    uptime_pct          NUMERIC(6,3) CHECK (uptime_pct BETWEEN 0 AND 100),
    uptime_imputed      BOOLEAN NOT NULL DEFAULT FALSE,
    support_tickets     INTEGER CHECK (support_tickets >= 0),
    marketing_spend     NUMERIC(14,2),
    opex                NUMERIC(14,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (op_date, region_id, bu_id)
);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id         VARCHAR(12) PRIMARY KEY,
    region_id           VARCHAR(8) NOT NULL REFERENCES regions(region_id),
    bu_id               VARCHAR(8) REFERENCES business_units(bu_id),
    supplier_id         VARCHAR(8) REFERENCES suppliers(supplier_id),
    severity            TEXT NOT NULL CHECK (severity IN ('SEV1', 'SEV2', 'SEV3', 'SEV4')),
    category            TEXT,
    opened_at           TIMESTAMPTZ NOT NULL,
    resolved_at         TIMESTAMPTZ CHECK (resolved_at IS NULL OR resolved_at >= opened_at),
    cost_impact         NUMERIC(14,2) CHECK (cost_impact >= 0),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
