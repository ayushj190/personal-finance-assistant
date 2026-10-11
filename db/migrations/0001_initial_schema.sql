-- 0001 Initial Schema & Seed
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

-- ── Accounts ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
  id              INTEGER PRIMARY KEY,
  provider        TEXT NOT NULL CHECK (provider IN ('enable_banking','etoro','trade_republic','manual')),
  institution     TEXT NOT NULL,
  external_id     TEXT,
  iban            TEXT,
  name            TEXT NOT NULL,
  currency        TEXT NOT NULL DEFAULT 'EUR',
  asset_class     TEXT NOT NULL CHECK (asset_class IN ('cash','investment','liability')),
  apy             REAL,
  is_active       INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (provider, external_id)
);

-- Daily balance history -> net-worth-over-time chart
CREATE TABLE IF NOT EXISTS account_snapshots (
  account_id      INTEGER NOT NULL REFERENCES accounts(id),
  snapshot_date   TEXT NOT NULL,
  balance_minor   INTEGER NOT NULL,
  balance_eur_minor INTEGER NOT NULL,
  PRIMARY KEY (account_id, snapshot_date)
);

-- ── Categories ────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS categories (
  id        INTEGER PRIMARY KEY,
  name      TEXT NOT NULL,
  parent_id INTEGER REFERENCES categories(id),
  kind      TEXT NOT NULL CHECK (kind IN ('income','fixed','discretionary','savings','transfer')),
  UNIQUE (name, parent_id)
);

-- ── Transactions ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS transactions (
  id                  INTEGER PRIMARY KEY,
  account_id          INTEGER NOT NULL REFERENCES accounts(id),
  dedup_hash          TEXT NOT NULL,
  external_ref        TEXT,
  booking_date        TEXT NOT NULL,
  value_date          TEXT,
  amount_minor        INTEGER NOT NULL,
  currency            TEXT NOT NULL,
  amount_eur_minor    INTEGER NOT NULL,
  description_raw     TEXT NOT NULL,
  counterparty_name   TEXT,
  counterparty_iban   TEXT,
  merchant_normalized TEXT,
  mcc                 TEXT,
  category_id         INTEGER REFERENCES categories(id),
  category_source     TEXT CHECK (category_source IN ('mcc','rule','llm','user')),
  is_internal_transfer INTEGER NOT NULL DEFAULT 0,
  source              TEXT NOT NULL CHECK (source IN ('api','csv','mt940','camt053','pdf')),
  imported_at         TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (account_id, dedup_hash)
);
CREATE INDEX IF NOT EXISTS ix_tx_date     ON transactions(booking_date);
CREATE INDEX IF NOT EXISTS ix_tx_merchant ON transactions(merchant_normalized);
CREATE INDEX IF NOT EXISTS ix_tx_category ON transactions(category_id);

-- ── Holdings (current positions; history via snapshots) ──
CREATE TABLE IF NOT EXISTS holdings (
  id              INTEGER PRIMARY KEY,
  account_id      INTEGER NOT NULL REFERENCES accounts(id),
  ticker          TEXT NOT NULL,
  isin            TEXT,
  name            TEXT,
  asset_type      TEXT NOT NULL CHECK (asset_type IN ('etf','stock','crypto','bond','commodity','other')),
  region          TEXT,
  sector          TEXT,
  quantity        REAL NOT NULL,
  cost_basis_minor INTEGER,
  currency        TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  UNIQUE (account_id, ticker)
);

-- ── Market quotes + FX (FX stored as ticker 'EURUSD=X') ──
CREATE TABLE IF NOT EXISTS market_quotes (
  ticker      TEXT NOT NULL,
  quote_date  TEXT NOT NULL,
  close       REAL NOT NULL,
  prev_close  REAL,
  currency    TEXT,
  fetched_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (ticker, quote_date)
);

-- ── Liabilities (mortgage parts) ──────────────────────────
CREATE TABLE IF NOT EXISTS liabilities (
  id                   INTEGER PRIMARY KEY,
  name                 TEXT NOT NULL,
  lender               TEXT NOT NULL DEFAULT 'ABN AMRO',
  loan_type            TEXT NOT NULL CHECK (loan_type IN ('annuity','linear','interest_only')),
  original_principal_minor INTEGER NOT NULL,
  home_value_minor     INTEGER,
  start_date           TEXT NOT NULL,
  term_months          INTEGER NOT NULL DEFAULT 360,
  payment_match_pattern TEXT,
  balance_override_minor INTEGER,
  balance_override_date  TEXT
);

CREATE TABLE IF NOT EXISTS liability_rate_periods (
  liability_id  INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
  from_date     TEXT NOT NULL,
  annual_rate   REAL NOT NULL,
  fixed_until   TEXT,
  PRIMARY KEY (liability_id, from_date)
);

CREATE TABLE IF NOT EXISTS liability_extra_payments (
  liability_id  INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
  paid_date     TEXT NOT NULL,
  amount_minor  INTEGER NOT NULL,
  recalc        TEXT NOT NULL DEFAULT 'lower_payment' CHECK (recalc IN ('lower_payment','shorter_term')),
  PRIMARY KEY (liability_id, paid_date)
);

CREATE TABLE IF NOT EXISTS liability_schedule (
  liability_id    INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
  month_idx       INTEGER NOT NULL,
  due_date        TEXT NOT NULL,
  payment_minor   INTEGER NOT NULL,
  interest_minor  INTEGER NOT NULL,
  principal_minor INTEGER NOT NULL,
  extra_minor     INTEGER NOT NULL DEFAULT 0,
  balance_minor   INTEGER NOT NULL,
  PRIMARY KEY (liability_id, month_idx)
);

-- ── Categorization cache ──────────────────────────────────
CREATE TABLE IF NOT EXISTS merchant_category_rules (
  id                  INTEGER PRIMARY KEY,
  merchant_normalized TEXT NOT NULL UNIQUE,
  category_id         INTEGER NOT NULL REFERENCES categories(id),
  source              TEXT NOT NULL CHECK (source IN ('llm','user','seed')),
  confidence          REAL,
  hit_count           INTEGER NOT NULL DEFAULT 0,
  created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Allocation profiles + targets ─────────────────────────
CREATE TABLE IF NOT EXISTS allocation_profiles (
  id          INTEGER PRIMARY KEY,
  name        TEXT NOT NULL UNIQUE,
  dimension   TEXT NOT NULL CHECK (dimension IN ('asset_class','asset_type','region','sector','currency','ticker')),
  include_cash INTEGER NOT NULL DEFAULT 0,
  drift_band_pct REAL NOT NULL DEFAULT 5,
  is_active   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS allocation_targets (
  profile_id  INTEGER NOT NULL REFERENCES allocation_profiles(id) ON DELETE CASCADE,
  bucket      TEXT NOT NULL,
  target_pct  REAL NOT NULL CHECK (target_pct BETWEEN 0 AND 100),
  PRIMARY KEY (profile_id, bucket)
);

-- ── Sync log (status badges in Settings) ─────────────────
CREATE TABLE IF NOT EXISTS sync_log (
  id         INTEGER PRIMARY KEY,
  connector  TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  status     TEXT NOT NULL CHECK (status IN ('ok','error','needs_reauth')),
  inserted   INTEGER DEFAULT 0,
  message    TEXT
);

-- ── LLM-facing and reporting views ───────────────────────
CREATE VIEW IF NOT EXISTS v_transactions AS
SELECT t.id, t.booking_date, a.institution, a.name AS account,
       t.amount_eur_minor / 100.0 AS amount_eur, t.currency,
       t.merchant_normalized AS merchant, c.name AS category,
       p.name AS parent_category, c.kind AS category_kind,
       t.is_internal_transfer
FROM transactions t
JOIN accounts a ON a.id = t.account_id
LEFT JOIN categories c ON c.id = t.category_id
LEFT JOIN categories p ON p.id = c.parent_id;

CREATE VIEW IF NOT EXISTS v_net_worth_daily AS
SELECT s.snapshot_date AS date, a.asset_class,
       SUM(s.balance_eur_minor) / 100.0 AS value_eur
FROM account_snapshots s JOIN accounts a ON a.id = s.account_id
GROUP BY s.snapshot_date, a.asset_class;

CREATE VIEW IF NOT EXISTS v_holdings AS
SELECT h.id, a.institution, a.name AS account, h.ticker, h.isin, h.name,
       h.asset_type, h.region, h.sector, h.quantity,
       ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS cost_basis,
       h.cost_basis_minor / 100.0 AS cost_basis_native,
       h.currency,
       COALESCE(mq.close, 0) AS latest_close,
       COALESCE(mq.prev_close, mq.close, 0) AS prev_close,
       (h.quantity * COALESCE(mq.close, 0) * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS value_eur,
       ((h.quantity * COALESCE(mq.close, 0) * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
        - ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))) AS unrealized_pnl_eur,
       h.updated_at
FROM holdings h
JOIN accounts a ON a.id = h.account_id
LEFT JOIN (
  SELECT ticker, close, prev_close, currency
  FROM market_quotes
  WHERE (ticker, quote_date) IN (SELECT ticker, MAX(quote_date) FROM market_quotes GROUP BY ticker)
) mq ON mq.ticker = h.ticker
LEFT JOIN (
  SELECT close
  FROM market_quotes
  WHERE ticker = 'EURUSD=X' AND quote_date = (SELECT MAX(quote_date) FROM market_quotes WHERE ticker = 'EURUSD=X')
) fx ON 1=1;

CREATE VIEW IF NOT EXISTS v_monthly_cashflow AS
SELECT strftime('%Y-%m', t.booking_date) AS month,
       SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor > 0 THEN 'income' ELSE 'discretionary' END) = 'income' THEN t.amount_eur_minor ELSE 0 END) / 100.0 AS income_eur,
       SUM(CASE WHEN c.kind = 'fixed' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS fixed_eur,
       SUM(CASE WHEN COALESCE(c.kind, CASE WHEN t.amount_eur_minor < 0 THEN 'discretionary' ELSE '' END) = 'discretionary' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS discretionary_eur,
       SUM(CASE WHEN c.kind = 'savings' THEN -t.amount_eur_minor ELSE 0 END) / 100.0 AS savings_eur
FROM transactions t
LEFT JOIN categories c ON c.id = t.category_id
WHERE t.is_internal_transfer = 0
GROUP BY strftime('%Y-%m', t.booking_date);

CREATE VIEW IF NOT EXISTS v_mortgage_payments AS
SELECT l.name AS loan_name, l.lender, s.month_idx, s.due_date,
       s.payment_minor / 100.0 AS payment_eur,
       s.interest_minor / 100.0 AS interest_eur,
       s.principal_minor / 100.0 AS principal_eur,
       s.extra_minor / 100.0 AS extra_eur,
       s.balance_minor / 100.0 AS balance_eur
FROM liability_schedule s
JOIN liabilities l ON l.id = s.liability_id;

-- ── Risk Profile & Assessment ─────────────────────────────
CREATE TABLE IF NOT EXISTS risk_profiles (
  id              INTEGER PRIMARY KEY,
  assessed_date   TEXT NOT NULL DEFAULT (datetime('now')),
  risk_score      INTEGER NOT NULL,
  risk_tolerance  TEXT NOT NULL,
  notes           TEXT,
  investment_horizon_years INTEGER,
  liquidity_needs TEXT,
  investment_experience TEXT
);

CREATE TABLE IF NOT EXISTS risk_questionnaire_answers (
  id              INTEGER PRIMARY KEY,
  profile_id      INTEGER NOT NULL REFERENCES risk_profiles(id) ON DELETE CASCADE,
  question        TEXT NOT NULL,
  answer          TEXT NOT NULL
);

-- ── Tax Profile ───────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tax_profile (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  gross_annual_income INTEGER NOT NULL,
  has_fiscal_partner INTEGER NOT NULL DEFAULT 0,
  has_30_percent_ruling INTEGER NOT NULL DEFAULT 0,
  is_entrepreneur INTEGER NOT NULL DEFAULT 0,
  owns_home INTEGER NOT NULL DEFAULT 0,
  birth_year INTEGER,
  has_13th_month INTEGER NOT NULL DEFAULT 0,
  expected_bonus_eur INTEGER NOT NULL DEFAULT 0,
  pension_contribution_pct REAL NOT NULL DEFAULT 0,
  employer_pension_match_pct REAL NOT NULL DEFAULT 0,
  factor_a_minor INTEGER NOT NULL DEFAULT 0,
  green_investments_minor INTEGER NOT NULL DEFAULT 0,
  reserveringsruimte_minor INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Goals ───────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,
  target_amount   REAL NOT NULL,
  target_date     TEXT,
  account_id      INTEGER REFERENCES accounts(id) ON DELETE SET NULL,
  created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── Local RAG Knowledge Embeddings ──────────────────────
CREATE TABLE IF NOT EXISTS knowledge_embeddings (
  id              INTEGER PRIMARY KEY,
  chunk_id        TEXT UNIQUE NOT NULL,
  doc_title       TEXT NOT NULL,
  category        TEXT NOT NULL,
  content         TEXT NOT NULL,
  embedding_json  TEXT,
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- ── App Settings ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_settings (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- ── Categories Taxonomy Seed ──────────────────────────────
INSERT OR IGNORE INTO categories (id, name, parent_id, kind) VALUES
  (1, 'Income', NULL, 'income'),
  (2, 'Salary', 1, 'income'),
  (3, 'Bonus & Benefits', 1, 'income'),
  (4, 'Investment Returns', 1, 'income'),
  (5, 'Other Income', 1, 'income'),
  (6, 'Interest', 1, 'income'),

  (10, 'Mortgage & Rent', NULL, 'fixed'),
  (11, 'Mortgage', 10, 'fixed'),
  (12, 'Rent', 10, 'fixed'),

  (103, 'Utility Bills', NULL, 'fixed'),
  (13, 'Electricity & Gas', 103, 'fixed'),
  (14, 'Water', 103, 'fixed'),
  (15, 'Internet & Telecom', 103, 'fixed'),
  (16, 'Municipal Taxes', 103, 'fixed'),

  (20, 'Insurances', NULL, 'fixed'),
  (21, 'Health Insurance', 20, 'fixed'),
  (22, 'Home & Liability Insurance', 20, 'fixed'),
  (23, 'Bank & Service Fees', 20, 'fixed'),

  (30, 'Subscriptions', NULL, 'fixed'),
  (31, 'Streaming & Media', 30, 'fixed'),
  (32, 'Software & Cloud', 30, 'fixed'),

  (40, 'Groceries', NULL, 'discretionary'),
  (41, 'Supermarket', 40, 'discretionary'),
  (42, 'Pharmacy & Drugstore', 40, 'discretionary'),
  (43, 'Home & Maintenance', 40, 'discretionary'),

  (50, 'Food & Restaurants', NULL, 'discretionary'),
  (51, 'Restaurants', 50, 'discretionary'),
  (52, 'Cafes & Bakeries', 50, 'discretionary'),
  (53, 'Bars & Nightlife', 50, 'discretionary'),
  (54, 'Food Delivery & Takeaway', 50, 'discretionary'),

  (104, 'Sports & Leisure', NULL, 'discretionary'),
  (33, 'Gym & Fitness', 104, 'discretionary'),
  (65, 'Hobbies & Entertainment', 104, 'discretionary'),
  (83, 'Vacation Activities', 104, 'discretionary'),

  (60, 'Shopping & Personal', NULL, 'discretionary'),
  (61, 'Clothing & Shoes', 60, 'discretionary'),
  (62, 'Electronics & Gadgets', 60, 'discretionary'),
  (63, 'Personal Care', 60, 'discretionary'),
  (64, 'Gifts & Donations', 60, 'discretionary'),

  (70, 'Transportation', NULL, 'discretionary'),
  (71, 'Public Transit', 70, 'discretionary'),
  (72, 'Fuel', 70, 'discretionary'),
  (73, 'Parking & Tolls', 70, 'discretionary'),
  (74, 'Car Maintenance', 70, 'discretionary'),
  (75, 'Taxis & Rideshare', 70, 'discretionary'),

  (80, 'Travel & Holidays', NULL, 'discretionary'),
  (81, 'Flights', 80, 'discretionary'),
  (82, 'Lodging & Hotels', 80, 'discretionary'),

  (90, 'Savings & Investments', NULL, 'savings'),
  (91, 'Brokerage Deposits', 90, 'savings'),
  (92, 'Crypto Purchases', 90, 'savings'),
  (93, 'Pension Contributions', 90, 'savings'),

  (100, 'Transfers', NULL, 'transfer'),
  (101, 'Internal Transfer', 100, 'transfer'),
  (102, 'Credit Card Repayment', 100, 'transfer');

-- Default allocation profiles and targets
INSERT OR IGNORE INTO allocation_profiles (id, name, dimension, include_cash, drift_band_pct, is_active) VALUES
  (1, '80/20 Core-Satellite', 'asset_type', 0, 5.0, 1),
  (2, 'Global One-Fund', 'ticker', 0, 5.0, 0),
  (3, 'Asset Class & Cash Buffer', 'asset_class', 1, 5.0, 0);

INSERT OR IGNORE INTO allocation_targets (profile_id, bucket, target_pct) VALUES
  (1, 'etf', 80.0),
  (1, 'stock', 15.0),
  (1, 'crypto', 5.0),
  (2, 'VWCE.DE', 100.0),
  (3, 'cash', 10.0),
  (3, 'investment', 90.0);

-- Performance Indexes
CREATE INDEX IF NOT EXISTS ix_snapshots_date ON account_snapshots(snapshot_date);
CREATE INDEX IF NOT EXISTS ix_tx_acc_date ON transactions(account_id, booking_date);
CREATE INDEX IF NOT EXISTS ix_holdings_acc_ticker ON holdings(account_id, ticker);
