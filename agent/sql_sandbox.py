import sqlite3
import time
from typing import Any
import pandas as pd

from config import DB_PATH

DISALLOWED_ACTIONS = {
    sqlite3.SQLITE_INSERT,
    sqlite3.SQLITE_UPDATE,
    sqlite3.SQLITE_DELETE,
    sqlite3.SQLITE_CREATE_TABLE,
    sqlite3.SQLITE_DROP_TABLE,
    sqlite3.SQLITE_ALTER_TABLE,
    sqlite3.SQLITE_PRAGMA,
    sqlite3.SQLITE_ATTACH,
    sqlite3.SQLITE_DETACH,
}


def _authorizer(action: int, _arg1: Any, arg2: Any, _db: Any, _trigger: Any) -> int:
    if action in DISALLOWED_ACTIONS:
        return sqlite3.SQLITE_DENY
    if action == sqlite3.SQLITE_SELECT or action == sqlite3.SQLITE_READ:
        return sqlite3.SQLITE_OK
    if action == sqlite3.SQLITE_FUNCTION:
        func_name = str(arg2).lower()
        if func_name in {"load_extension"}:
            return sqlite3.SQLITE_DENY
        return sqlite3.SQLITE_OK
    return sqlite3.SQLITE_DENY


def execute_safe_query(
    sql: str,
    db_path: str | None = None,
    timeout_seconds: float = 5.0,
    max_rows: int = 5000,
) -> pd.DataFrame:
    path = db_path or str(DB_PATH)
    clean_sql = sql.strip().rstrip(";")
    if ";" in clean_sql:
        raise ValueError("Single SQL statement only.")

    start_time = time.time()

    def deadline_check() -> int:
        if time.time() - start_time > timeout_seconds:
            return 1  # non-zero aborts query
        return 0

    # URI read-only connection
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.set_authorizer(_authorizer)
        conn.set_progress_handler(deadline_check, 1000)
        cur = conn.cursor()
        cur.execute(clean_sql)
        cols = [desc[0] for desc in cur.description] if cur.description else []
        rows = cur.fetchmany(max_rows)
        return pd.DataFrame(rows, columns=cols)
    finally:
        conn.close()
