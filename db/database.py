import sqlite3
from pathlib import Path
from typing import Any, Iterable

from config import DB_PATH

DB_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = DB_DIR / "schema.sql"
SEED_FILE = DB_DIR / "seed.sql"


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


from db.migrations.runner import run_migrations


def migrate(db_path: Path | str = DB_PATH) -> None:
    conn = connect(db_path)
    try:
        run_migrations(conn)
    finally:
        conn.close()




def upsert_account(conn: sqlite3.Connection, acc: dict[str, Any]) -> int:
    query = """
    INSERT INTO accounts (provider, institution, external_id, iban, name, currency, asset_class, apy, is_active)
    VALUES (:provider, :institution, :external_id, :iban, :name, :currency, :asset_class, :apy, :is_active)
    ON CONFLICT(provider, external_id) DO UPDATE SET
        name = excluded.name,
        iban = COALESCE(excluded.iban, accounts.iban),
        currency = excluded.currency,
        asset_class = excluded.asset_class,
        apy = COALESCE(excluded.apy, accounts.apy),
        is_active = excluded.is_active;
    """
    params = {
        "provider": acc["provider"],
        "institution": acc["institution"],
        "external_id": acc.get("external_id"),
        "iban": acc.get("iban"),
        "name": acc["name"],
        "currency": acc.get("currency", "EUR"),
        "asset_class": acc.get("asset_class", "cash"),
        "apy": acc.get("apy"),
        "is_active": acc.get("is_active", 1),
    }
    with conn:
        conn.execute(query, params)
        row = conn.execute(
            "SELECT id FROM accounts WHERE provider = ? AND external_id = ?",
            (params["provider"], params["external_id"]),
        ).fetchone()
        return row[0] if row else 0


def get_account_by_provider_ext_id(conn: sqlite3.Connection, provider: str, ext_id: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM accounts WHERE provider = ? AND external_id = ?",
        (provider, ext_id),
    ).fetchone()


def upsert_transactions(conn: sqlite3.Connection, txs: Iterable[dict[str, Any]]) -> int:
    query = """
    INSERT INTO transactions (
        account_id, dedup_hash, external_ref, booking_date, value_date,
        amount_minor, currency, amount_eur_minor, description_raw,
        counterparty_name, counterparty_iban, merchant_normalized,
        mcc, category_id, category_source, is_internal_transfer, source
    ) VALUES (
        :account_id, :dedup_hash, :external_ref, :booking_date, :value_date,
        :amount_minor, :currency, :amount_eur_minor, :description_raw,
        :counterparty_name, :counterparty_iban, :merchant_normalized,
        :mcc, :category_id, :category_source, :is_internal_transfer, :source
    ) ON CONFLICT(account_id, dedup_hash) DO NOTHING;
    """
    inserted = 0
    with conn:
        for tx in txs:
            row_dict = {
                "account_id": tx["account_id"],
                "dedup_hash": tx["dedup_hash"],
                "external_ref": tx.get("external_ref"),
                "booking_date": tx["booking_date"],
                "value_date": tx.get("value_date"),
                "amount_minor": tx["amount_minor"],
                "currency": tx.get("currency", "EUR"),
                "amount_eur_minor": tx["amount_eur_minor"],
                "description_raw": tx["description_raw"],
                "counterparty_name": tx.get("counterparty_name"),
                "counterparty_iban": tx.get("counterparty_iban"),
                "merchant_normalized": tx.get("merchant_normalized"),
                "mcc": tx.get("mcc"),
                "category_id": tx.get("category_id"),
                "category_source": tx.get("category_source"),
                "is_internal_transfer": tx.get("is_internal_transfer", 0),
                "source": tx.get("source", "csv"),
            }
            cur = conn.execute(query, row_dict)
            if cur.rowcount > 0:
                inserted += cur.rowcount
    return inserted


def upsert_snapshots(conn: sqlite3.Connection, snapshots: Iterable[dict[str, Any]]) -> None:
    query = """
    INSERT INTO account_snapshots (account_id, snapshot_date, balance_minor, balance_eur_minor)
    VALUES (:account_id, :snapshot_date, :balance_minor, :balance_eur_minor)
    ON CONFLICT(account_id, snapshot_date) DO UPDATE SET
        balance_minor = excluded.balance_minor,
        balance_eur_minor = excluded.balance_eur_minor;
    """
    with conn:
        conn.executemany(query, snapshots)


def upsert_holdings(conn: sqlite3.Connection, holdings: Iterable[dict[str, Any]]) -> None:
    query = """
    INSERT INTO holdings (
        account_id, ticker, isin, name, asset_type, region, sector,
        quantity, cost_basis_minor, currency, status, closed_at, updated_at
    ) VALUES (
        :account_id, :ticker, :isin, :name, :asset_type, :region, :sector,
        :quantity, :cost_basis_minor, :currency, :status, :closed_at, :updated_at
    ) ON CONFLICT(account_id, ticker) DO UPDATE SET
        quantity = excluded.quantity,
        cost_basis_minor = excluded.cost_basis_minor,
        updated_at = excluded.updated_at,
        status = excluded.status,
        closed_at = excluded.closed_at,
        name = COALESCE(excluded.name, holdings.name),
        isin = COALESCE(excluded.isin, holdings.isin),
        asset_type = COALESCE(excluded.asset_type, holdings.asset_type),
        region = COALESCE(excluded.region, holdings.region),
        sector = COALESCE(excluded.sector, holdings.sector);
    """
    records = []
    for h in holdings:
        rec = {
            "account_id": h["account_id"],
            "ticker": h["ticker"],
            "isin": h.get("isin"),
            "name": h.get("name"),
            "asset_type": h.get("asset_type", "stock"),
            "region": h.get("region"),
            "sector": h.get("sector"),
            "quantity": float(h.get("quantity", 0.0)),
            "cost_basis_minor": h.get("cost_basis_minor"),
            "currency": h.get("currency", "EUR"),
            "status": h.get("status", "active"),
            "closed_at": h.get("closed_at"),
            "updated_at": h.get("updated_at") or pd.Timestamp.now().isoformat(),
        }
        records.append(rec)
    with conn:
        conn.executemany(query, records)


def upsert_market_quotes(conn: sqlite3.Connection, quotes: Iterable[dict[str, Any]]) -> None:
    query = """
    INSERT INTO market_quotes (ticker, quote_date, close, prev_close, currency, fetched_at)
    VALUES (:ticker, :quote_date, :close, :prev_close, :currency, datetime('now'))
    ON CONFLICT(ticker, quote_date) DO UPDATE SET
        close = excluded.close,
        prev_close = COALESCE(excluded.prev_close, market_quotes.prev_close),
        currency = excluded.currency,
        fetched_at = datetime('now');
    """
    with conn:
        conn.executemany(query, quotes)


def upsert_category_rule(
    conn: sqlite3.Connection,
    merchant_normalized: str,
    category_id: int,
    source: str = "user",
    confidence: float | None = 1.0,
) -> None:
    query = """
    INSERT INTO merchant_category_rules (merchant_normalized, category_id, source, confidence, hit_count, created_at)
    VALUES (?, ?, ?, ?, 1, datetime('now'))
    ON CONFLICT(merchant_normalized) DO UPDATE SET
        category_id = excluded.category_id,
        source = excluded.source,
        confidence = excluded.confidence,
        hit_count = merchant_category_rules.hit_count + 1;
    """
    with conn:
        conn.execute(query, (merchant_normalized,
                     category_id, source, confidence))


def get_rules_cache(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute(
        "SELECT merchant_normalized, category_id FROM merchant_category_rules").fetchall()
    return {r["merchant_normalized"]: r["category_id"] for r in rows}


def get_category_map(conn: sqlite3.Connection) -> dict[str, int]:
    rows = conn.execute("SELECT id, name FROM categories").fetchall()
    return {r["name"]: r["id"] for r in rows}


def get_own_ibans(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT iban FROM accounts WHERE iban IS NOT NULL AND iban != ''").fetchall()
    ibans = {r["iban"].replace(" ", "").upper() for r in rows}
    try:
        val = get_setting(conn, "own_ibans")
        if val:
            if isinstance(val, str):
                for part in val.split(","):
                    if part.strip():
                        ibans.add(part.strip().replace(" ", "").upper())
            elif isinstance(val, (list, set)):
                for part in val:
                    ibans.add(str(part).strip().replace(" ", "").upper())
    except Exception:
        pass
    return ibans


def save_risk_profile(
    conn: sqlite3.Connection,
    risk_score: int,
    risk_tolerance: str,
    notes: str = "",
    answers: dict[str, str] | None = None,
    investment_horizon_years: int | None = None,
    liquidity_needs: str | None = None,
    investment_experience: str | None = None,
) -> int:
    with conn:
        cur = conn.execute(
            """
            INSERT INTO risk_profiles (risk_score, risk_tolerance, notes, investment_horizon_years, liquidity_needs, investment_experience)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (risk_score, risk_tolerance, notes, investment_horizon_years, liquidity_needs, investment_experience),
        )
        profile_id = cur.lastrowid
        if answers:
            for q, a in answers.items():
                conn.execute(
                    """
                    INSERT INTO risk_questionnaire_answers (profile_id, question, answer)
                    VALUES (?, ?, ?)
                    """,
                    (profile_id, str(q), str(a)),
                )
        return profile_id


def get_latest_risk_profile(conn: sqlite3.Connection) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM risk_profiles ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    res = dict(row)
    answers = conn.execute(
        "SELECT question, answer FROM risk_questionnaire_answers WHERE profile_id = ?",
        (res["id"],),
    ).fetchall()
    res["answers"] = {a["question"]: a["answer"] for a in answers}
    return res


def get_setting(conn: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """Retrieve value from app_settings table."""
    try:
        row = conn.execute("SELECT value FROM app_settings WHERE key = ?", (key,)).fetchone()
        if row is not None:
            return row["value"]
    except Exception:
        pass
    return default


def set_setting(conn: sqlite3.Connection, key: str, value: Any) -> None:
    """Upsert value in app_settings table."""
    with conn:
        conn.execute(
            """
            INSERT INTO app_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(key), str(value)),
        )


def add_custom_category(conn: sqlite3.Connection, name: str, kind: str, parent_id: int | None = None) -> int:
    """Add a new custom expense category or return existing id."""
    clean_name = name.strip()
    with conn:
        if parent_id is None:
            existing = conn.execute(
                "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND parent_id IS NULL",
                (clean_name,),
            ).fetchone()
        else:
            existing = conn.execute(
                "SELECT id FROM categories WHERE LOWER(name) = LOWER(?) AND parent_id = ?",
                (clean_name, parent_id),
            ).fetchone()
        if existing:
            return int(existing["id"] if isinstance(existing, sqlite3.Row) else existing[0])

        cur = conn.execute(
            "INSERT INTO categories (name, parent_id, kind) VALUES (?, ?, ?)",
            (clean_name, parent_id, kind),
        )
        return cur.lastrowid


def delete_transaction(conn: sqlite3.Connection, transaction_id: int) -> bool:
    """Delete a single transaction by ID."""
    with conn:
        cur = conn.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
        return cur.rowcount > 0


def delete_transactions(conn: sqlite3.Connection, transaction_ids: Iterable[int]) -> int:
    """Delete multiple transactions by IDs."""
    ids = [int(i) for i in transaction_ids]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with conn:
        cur = conn.execute(f"DELETE FROM transactions WHERE id IN ({placeholders})", ids)
        return cur.rowcount


