"""Remove the seeded default allocation strategies and admit the ``nature`` dimension.

The initial schema seeded three starter profiles (80/20 Core-Satellite, Global
One-Fund, Asset Class & Cash Buffer) whose stock-vs-ETF framing is not useful.
Users steer allocation by sector/theme, region, currency, and asset nature
(equities, bonds, commodities, crypto) instead.

SQLite cannot alter a column CHECK, so the table is rebuilt with the widened
vocabulary. Rows are snapshotted first because dropping the parent cascades into
``allocation_targets``. Any profile the user created is preserved.
"""

from __future__ import annotations

import sqlite3

SEEDED_PROFILE_NAMES = (
    "80/20 core-satellite",
    "global one-fund",
    "asset class & cash buffer",
)

_CREATE_PROFILES = """
CREATE TABLE allocation_profiles (
  id             INTEGER PRIMARY KEY,
  name           TEXT NOT NULL UNIQUE,
  dimension      TEXT NOT NULL CHECK (
                   dimension IN ('sector','region','currency','nature',
                                 'asset_class','asset_type','ticker')
                 ),
  include_cash   INTEGER NOT NULL DEFAULT 0,
  drift_band_pct REAL NOT NULL DEFAULT 5,
  is_active      INTEGER NOT NULL DEFAULT 0
);
"""


def migrate(conn: sqlite3.Connection) -> None:
    profiles = conn.execute(
        "SELECT id, name, dimension, include_cash, drift_band_pct, is_active "
        "FROM allocation_profiles"
    ).fetchall()
    targets = conn.execute(
        "SELECT profile_id, bucket, target_pct FROM allocation_targets"
    ).fetchall()

    conn.execute("DROP TABLE allocation_profiles")
    conn.execute(_CREATE_PROFILES)

    kept = [p for p in profiles if str(p["name"]).strip().lower() not in SEEDED_PROFILE_NAMES]
    kept_ids = {p["id"] for p in kept}

    conn.execute("DELETE FROM allocation_targets")
    conn.executemany(
        "INSERT INTO allocation_profiles "
        "(id, name, dimension, include_cash, drift_band_pct, is_active) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [tuple(p) for p in kept],
    )
    conn.executemany(
        "INSERT INTO allocation_targets (profile_id, bucket, target_pct) VALUES (?, ?, ?)",
        [tuple(t) for t in targets if t["profile_id"] in kept_ids],
    )
