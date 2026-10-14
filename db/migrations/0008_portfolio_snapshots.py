"""Migration 0008: Add portfolio_snapshots table for daily portfolio equity curve.

Holds daily portfolio market value, cost basis, and day P&L in euro minor units
(cents) to power the equity curve and history without recalculating from historical closes.
"""

from __future__ import annotations

import sqlite3

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
  snapshot_date          TEXT PRIMARY KEY,
  market_value_eur_minor INTEGER NOT NULL,
  cost_basis_eur_minor   INTEGER NOT NULL,
  day_pnl_eur_minor      INTEGER,
  fetched_at             TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute(_CREATE_TABLE)
