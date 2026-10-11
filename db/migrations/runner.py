import re
import sqlite3
from pathlib import Path
from typing import Optional

MIGRATIONS_DIR = Path(__file__).resolve().parent


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return current integer schema version from schema_version table."""
    conn.execute("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);")
    row = conn.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    if row is not None:
        return int(row[0] if isinstance(row, (tuple, list)) else row["version"])
    return 0


def get_available_migrations(migrations_dir: Optional[Path] = None) -> list[tuple[int, str, Path]]:
    """Scan directory for files matching NNNN_name.sql and return sorted by version."""
    target_dir = migrations_dir or MIGRATIONS_DIR
    pattern = re.compile(r"^(\d{4})_(.+)\.sql$")
    migrations = []
    if target_dir.exists():
        for file_path in target_dir.glob("*.sql"):
            match = pattern.match(file_path.name)
            if match:
                version = int(match.group(1))
                name = match.group(2)
                migrations.append((version, name, file_path))
    migrations.sort(key=lambda m: m[0])
    return migrations


def run_migrations(conn: sqlite3.Connection, migrations_dir: Optional[Path] = None) -> list[int]:
    """Execute any pending schema migrations in order and update schema_version."""
    current_ver = get_current_version(conn)
    available = get_available_migrations(migrations_dir)
    pending = [m for m in available if m[0] > current_ver]

    if not pending:
        return []

    executed_versions = []
    with conn:
        for ver, name, path in pending:
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            conn.executescript(sql)
            conn.execute("DELETE FROM schema_version;")
            conn.execute("INSERT INTO schema_version (version) VALUES (?);", (ver,))
            executed_versions.append(ver)

    return executed_versions
