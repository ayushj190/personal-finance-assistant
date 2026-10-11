-- Migration: 0005_holdings_status_and_reconciliation.sql
-- Add status and closed_at lifecycle fields to holdings table and update v_holdings view filter

ALTER TABLE holdings ADD COLUMN status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed'));
ALTER TABLE holdings ADD COLUMN closed_at TEXT;

DROP VIEW IF EXISTS v_holdings;

CREATE VIEW v_holdings AS
SELECT h.id, a.institution, a.name AS account, h.ticker, h.isin, h.name,
       h.asset_type, h.region, h.sector, h.quantity,
       ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)) AS cost_basis,
       h.cost_basis_minor / 100.0 AS cost_basis_native,
       h.currency,
       COALESCE(mq.close, 0) AS latest_close,
       COALESCE(mq.prev_close, mq.close, 0) AS prev_close,
       (CASE 
          WHEN COALESCE(mq.close, 0) > 0 THEN 
            (h.quantity * mq.close * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
          ELSE 
            ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
        END) AS value_eur,
       (CASE 
          WHEN COALESCE(mq.close, 0) > 0 THEN 
            ((h.quantity * mq.close * (CASE WHEN COALESCE(mq.currency, h.currency) = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END))
             - ((COALESCE(h.cost_basis_minor, 0) / 100.0) * (CASE WHEN h.currency = 'USD' THEN (1.0 / COALESCE(fx.close, 1.0)) ELSE 1.0 END)))
          ELSE 0.0
        END) AS unrealized_pnl_eur,
       h.status,
       h.closed_at,
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
) fx ON 1=1
WHERE h.quantity > 0 AND h.status = 'active';
