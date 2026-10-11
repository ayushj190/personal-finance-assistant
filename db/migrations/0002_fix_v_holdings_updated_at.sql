-- Migration: 0002_fix_v_holdings_updated_at.sql
-- Ensure v_holdings view exposes updated_at column from holdings table

DROP VIEW IF EXISTS v_holdings;

CREATE VIEW v_holdings AS
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
