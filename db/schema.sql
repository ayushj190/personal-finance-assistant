PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);

-- ── Accounts ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS accounts (
  id              INTEGER PRIMARY KEY,
  provider        TEXT NOT NULL CHECK (provider IN ('enable_banking','etoro','trade_republic','manual')),
  institution     TEXT NOT NULL,                 -- 'ABN AMRO','Revolut','eToro','eToro Money','Trade Republic'
  external_id     TEXT,                          -- provider account uid
  iban            TEXT,
  name            TEXT NOT NULL,                 -- 'ABN Checking','ABN Savings'...
  currency        TEXT NOT NULL DEFAULT 'EUR',
  asset_class     TEXT NOT NULL CHECK (asset_class IN ('cash','investment','liability')),
  apy             REAL,                          -- annual percentage yield for savings accounts
  is_active       INTEGER NOT NULL DEFAULT 1,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE (provider, external_id)
);

-- Daily balance history -> net-worth-over-time chart
CREATE TABLE IF NOT EXISTS account_snapshots (
  account_id      INTEGER NOT NULL REFERENCES accounts(id),
  snapshot_date   TEXT NOT NULL,
  balance_minor   INTEGER NOT NULL,              -- native currency
  balance_eur_minor INTEGER NOT NULL,            -- FX-normalized at snapshot time
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
  dedup_hash          TEXT NOT NULL,             -- see normalization.dedup_hash()
  external_ref        TEXT,                      -- provider entry_reference if any
  booking_date        TEXT NOT NULL,
  value_date          TEXT,
  amount_minor        INTEGER NOT NULL,          -- signed: negative = outflow
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
  ticker          TEXT NOT NULL,                 -- yfinance symbol, e.g. 'VWCE.DE','AAPL','BTC-USD'
  isin            TEXT,
  name            TEXT,
  asset_type      TEXT NOT NULL CHECK (asset_type IN ('etf','stock','crypto','bond','commodity','other')),
  region          TEXT,                          -- 'Global','US','Europe','EM'…
  sector          TEXT,                          -- e.g. 'Technology', 'Financial Services', 'Diversified'
  quantity        REAL NOT NULL,
  cost_basis_minor INTEGER,                      -- total, native currency
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
  name                 TEXT NOT NULL,            -- 'Leningdeel 1'
  lender               TEXT NOT NULL DEFAULT 'ABN AMRO',
  loan_type            TEXT NOT NULL CHECK (loan_type IN ('annuity','linear','interest_only')),
  original_principal_minor INTEGER NOT NULL,
  start_date           TEXT NOT NULL,
  term_months          INTEGER NOT NULL DEFAULT 360,
  payment_match_pattern TEXT,                    -- regex to match payment tx
  balance_override_minor INTEGER,                -- from annual statement
  balance_override_date  TEXT
);

-- Rate periods: initial fixed period + resets (first row from start_date)
CREATE TABLE IF NOT EXISTS liability_rate_periods (
  liability_id  INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
  from_date     TEXT NOT NULL,
  annual_rate   REAL NOT NULL,                   -- 0.0385
  fixed_until   TEXT,                            -- e.g. start + 10y
  PRIMARY KEY (liability_id, from_date)
);

-- Extra (penalty-free) repayments
CREATE TABLE IF NOT EXISTS liability_extra_payments (
  liability_id  INTEGER NOT NULL REFERENCES liabilities(id) ON DELETE CASCADE,
  paid_date     TEXT NOT NULL,
  amount_minor  INTEGER NOT NULL,
  recalc        TEXT NOT NULL DEFAULT 'lower_payment' CHECK (recalc IN ('lower_payment','shorter_term')),
  PRIMARY KEY (liability_id, paid_date)
);

-- Materialized liability schedule
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
  name        TEXT NOT NULL UNIQUE,              -- '80/20 Global', 'My crypto cap'…
  dimension   TEXT NOT NULL CHECK (dimension IN ('asset_class','asset_type','region','sector','currency','ticker')),
  include_cash INTEGER NOT NULL DEFAULT 0,       -- treat liquid cash as a bucket
  drift_band_pct REAL NOT NULL DEFAULT 5,        -- absolute band (pp); relative 25% rule also checked
  is_active   INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS allocation_targets (
  profile_id  INTEGER NOT NULL REFERENCES allocation_profiles(id) ON DELETE CASCADE,
  bucket      TEXT NOT NULL,                     -- value of the dimension, e.g. 'etf','US','VWCE.DE'
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
        - ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))) AS unrealized_pnl_eur
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
  risk_score      INTEGER NOT NULL,              -- 1 to 10 scale
  risk_tolerance  TEXT NOT NULL,                 -- 'Conservative', 'Moderately Conservative', 'Moderate', 'Growth', 'Aggressive'
  notes           TEXT
);

CREATE TABLE IF NOT EXISTS risk_questionnaire_answers (
  id              INTEGER PRIMARY KEY,
  profile_id      INTEGER NOT NULL REFERENCES risk_profiles(id) ON DELETE CASCADE,
  question        TEXT NOT NULL,
  answer          TEXT NOT NULL
);

