from datetime import datetime
from pathlib import Path
import re
import sqlite3
from typing import Any, Iterable

from config import DB_PATH

DB_DIR = Path(__file__).resolve().parent
SCHEMA_FILE = DB_DIR / "schema.sql"
SEED_FILE = DB_DIR / "seed.sql"


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


READONLY_ALLOWED_ACTIONS = {
    sqlite3.SQLITE_SELECT,
    sqlite3.SQLITE_READ,
    sqlite3.SQLITE_FUNCTION,
    sqlite3.SQLITE_PRAGMA,
}

READONLY_DENIED_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
}


def readonly_authorizer(
    action_code: int,
    param1: str | None,
    param2: str | None,
    db_name: str | None,
    trigger_name: str | None,
) -> int:
    """SQLite engine authorizer callback permitting only read operations."""
    if action_code in READONLY_ALLOWED_ACTIONS:
        if action_code == sqlite3.SQLITE_PRAGMA:
            if param1 and param1.lower() in {
                "foreign_keys",
                "foreign_key_list",
                "table_info",
                "index_list",
                "index_info",
                "database_list",
                "user_version",
                "table_xinfo",
                "compile_options",
            }:
                return sqlite3.SQLITE_OK
            if param2 is None or param2 == "":
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def connect_readonly(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Connect to database with read only authorizer and URI mode=ro."""
    path_str = str(db_path)
    if path_str == ":memory:":
        conn = sqlite3.connect("file::memory:?mode=ro", uri=True, check_same_thread=False)
    else:
        resolved_path = Path(db_path).resolve().as_posix()
        conn = sqlite3.connect(f"file:{resolved_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.set_authorizer(readonly_authorizer)
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


def create_manual_account(
    conn: sqlite3.Connection,
    account_dict: dict[str, Any],
    initial_balance_minor: int | None = None,
) -> int:
    """
    Create or update a manual account and optionally record an initial balance snapshot.
    Returns the integer account ID.
    """
    provider = account_dict.get("provider", "manual")
    inst = account_dict.get("institution", "Manual")
    name = account_dict["name"]
    currency = account_dict.get("currency", "EUR").upper()
    asset_class = account_dict.get("asset_class", "cash")
    apy = account_dict.get("apy")
    iban = account_dict.get("iban")

    external_id = account_dict.get("external_id")
    if not external_id:
        slug = re.sub(r"[^a-zA-Z0-9]+", "_", f"{inst}_{name}_{currency}").strip("_").lower()
        external_id = f"manual_{slug}"

    with conn:
        acc_id = upsert_account(conn, {
            "provider": provider,
            "institution": inst,
            "external_id": external_id,
            "iban": iban,
            "name": name,
            "currency": currency,
            "asset_class": asset_class,
            "apy": apy,
            "is_active": account_dict.get("is_active", 1),
        })

        if initial_balance_minor is not None:
            today_iso = datetime.now().date().isoformat()
            upsert_snapshots(conn, [{
                "account_id": acc_id,
                "snapshot_date": today_iso,
                "balance_minor": initial_balance_minor,
                "balance_eur_minor": initial_balance_minor,
            }])

    return acc_id


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


def set_transactions_internal_transfer(
    conn: sqlite3.Connection,
    tx_ids: Iterable[int],
    is_transfer: bool = True,
) -> int:
    """Atomically set or clear is_internal_transfer flag for transaction IDs, auto-assigning transfer category when True."""
    ids = [int(i) for i in tx_ids]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with conn:
        if is_transfer:
            row = conn.execute(
                """
                SELECT id FROM categories
                WHERE LOWER(name) IN ('internal transfer', 'transfers', 'transfer') OR kind = 'transfer'
                ORDER BY
                    CASE
                        WHEN LOWER(name) = 'internal transfer' THEN 1
                        WHEN LOWER(name) = 'transfers' THEN 2
                        WHEN LOWER(name) = 'transfer' THEN 3
                        ELSE 4
                    END
                LIMIT 1
                """
            ).fetchone()
            transfer_cat_id = (row["id"] if isinstance(row, sqlite3.Row) else row[0]) if row else None
            if transfer_cat_id is not None:
                cur = conn.execute(
                    f"UPDATE transactions SET is_internal_transfer = 1, category_id = ?, category_source = 'user' WHERE id IN ({placeholders})",
                    [transfer_cat_id] + ids,
                )
            else:
                cur = conn.execute(
                    f"UPDATE transactions SET is_internal_transfer = 1 WHERE id IN ({placeholders})",
                    ids,
                )
        else:
            cur = conn.execute(
                f"UPDATE transactions SET is_internal_transfer = 0 WHERE id IN ({placeholders})",
                ids,
            )
        return cur.rowcount


def bulk_categorize_transactions(
    conn: sqlite3.Connection,
    tx_ids: Iterable[int],
    category_id: int,
    source: str = "user",
    update_rules: bool = False,
) -> int:
    """Atomically update category_id and category_source for multiple transactions, optionally upserting merchant rules."""
    ids = [int(i) for i in tx_ids]
    if not ids:
        return 0
    placeholders = ",".join("?" for _ in ids)
    with conn:
        if update_rules:
            rows = conn.execute(
                f"SELECT DISTINCT merchant_normalized FROM transactions WHERE id IN ({placeholders}) AND merchant_normalized IS NOT NULL AND merchant_normalized != ''",
                ids,
            ).fetchall()
            for r in rows:
                merchant = r["merchant_normalized"] if isinstance(r, sqlite3.Row) else r[0]
                if merchant:
                    upsert_category_rule(conn, merchant, category_id, source=source, confidence=1.0)
        cur = conn.execute(
            f"UPDATE transactions SET category_id = ?, category_source = ? WHERE id IN ({placeholders})",
            [category_id, source] + ids,
        )
        return cur.rowcount



