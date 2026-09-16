-- ============================================================
-- Marketplace Analytics — schema en etoile (Kimball)
-- 3 schemas : staging (brut type) / dwh (dimensionnel) / analytics (agregats)
-- ============================================================

CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS analytics;

-- ------------------------------------------------------------
-- STAGING : donnees brutes typees, chargees telles quelles
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS staging.orders (
    order_id    TEXT            NOT NULL,
    dt          DATE            NOT NULL,
    customer_id TEXT,
    seller_id   TEXT,
    product_id  TEXT,
    quantity    INT,
    unit_price  NUMERIC(10, 2),
    total       NUMERIC(12, 2),
    commission  NUMERIC(12, 2),
    status      TEXT,
    loaded_at   TIMESTAMPTZ     NOT NULL DEFAULT now(),
    PRIMARY KEY (order_id, dt)
);

-- Log d'ingestion des fichiers deposes dans MinIO (pattern TP6)
CREATE TABLE IF NOT EXISTS staging.file_ingestion_log (
    log_id       SERIAL PRIMARY KEY,
    object_key   TEXT        NOT NULL,
    bucket_name  TEXT        NOT NULL,
    source       TEXT        NOT NULL,
    status       TEXT        NOT NULL,
    message      TEXT,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ------------------------------------------------------------
-- DWH : dimensions + table de faits
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS dwh.dim_seller (
    seller_id   TEXT PRIMARY KEY,
    name        TEXT,
    country     TEXT,
    city        TEXT,
    joined_date DATE,
    rating      NUMERIC(2, 1)
);

CREATE TABLE IF NOT EXISTS dwh.dim_product (
    product_id TEXT PRIMARY KEY,
    name       TEXT,
    category   TEXT,
    price      NUMERIC(10, 2),
    seller_id  TEXT REFERENCES dwh.dim_seller (seller_id)
);

CREATE TABLE IF NOT EXISTS dwh.dim_date (
    dt          DATE PRIMARY KEY,
    year        INT  NOT NULL,
    month       INT  NOT NULL,
    day         INT  NOT NULL,
    day_of_week INT  NOT NULL,   -- 0 = lundi
    is_weekend  BOOL NOT NULL
);

-- Peuplement de dim_date sur 2025-2027 (idempotent)
INSERT INTO dwh.dim_date (dt, year, month, day, day_of_week, is_weekend)
SELECT
    d::DATE,
    EXTRACT(YEAR  FROM d)::INT,
    EXTRACT(MONTH FROM d)::INT,
    EXTRACT(DAY   FROM d)::INT,
    EXTRACT(ISODOW FROM d)::INT - 1,
    EXTRACT(ISODOW FROM d) >= 6
FROM generate_series('2025-01-01'::DATE, '2027-12-31'::DATE, '1 day') AS d
ON CONFLICT (dt) DO NOTHING;

CREATE TABLE IF NOT EXISTS dwh.fact_orders (
    order_id    TEXT            NOT NULL,
    dt          DATE            NOT NULL REFERENCES dwh.dim_date (dt),
    seller_id   TEXT            REFERENCES dwh.dim_seller (seller_id),
    product_id  TEXT            REFERENCES dwh.dim_product (product_id),
    customer_id TEXT,
    quantity    INT,
    unit_price  NUMERIC(10, 2),
    total       NUMERIC(12, 2),
    commission  NUMERIC(12, 2),
    status      TEXT,
    PRIMARY KEY (order_id, dt)
);

-- ------------------------------------------------------------
-- ANALYTICS : agregats pre-calcules pour Metabase
-- ------------------------------------------------------------

CREATE TABLE IF NOT EXISTS analytics.daily_summary (
    dt               DATE PRIMARY KEY,
    total_orders     INT,
    total_revenue    NUMERIC(14, 2),
    avg_basket       NUMERIC(12, 2),
    total_commission NUMERIC(14, 2),
    top_seller_id    TEXT
);

-- Bonus : CA par vendeur et par jour (dashboard Top Sellers)
CREATE TABLE IF NOT EXISTS analytics.seller_daily (
    dt          DATE NOT NULL,
    seller_id   TEXT NOT NULL,
    nb_orders   INT,
    revenue     NUMERIC(14, 2),
    commission  NUMERIC(14, 2),
    PRIMARY KEY (dt, seller_id)
);

-- Bonus : CA par categorie et par jour
CREATE TABLE IF NOT EXISTS analytics.category_daily (
    dt          DATE NOT NULL,
    category    TEXT NOT NULL,
    nb_orders   INT,
    revenue     NUMERIC(14, 2),
    PRIMARY KEY (dt, category)
);

-- Bonus : alertes de detection d'anomalies (US-05)
CREATE TABLE IF NOT EXISTS analytics.alerts (
    alert_id    SERIAL PRIMARY KEY,
    dt          DATE        NOT NULL,
    alert_type  TEXT        NOT NULL,
    message     TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
