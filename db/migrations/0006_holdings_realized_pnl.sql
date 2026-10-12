-- Migration: 0006_holdings_realized_pnl.sql
-- Add realized_pnl_minor and realized_proceeds_minor to holdings table for closed position tracking

ALTER TABLE holdings ADD COLUMN realized_pnl_minor INTEGER NOT NULL DEFAULT 0;
ALTER TABLE holdings ADD COLUMN realized_proceeds_minor INTEGER NOT NULL DEFAULT 0;
