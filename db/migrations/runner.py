"""Forward only, checksummed, transactional migration runner.

Migrations are files named ``NNNN_name.sql`` (schema) or ``NNNN_name.py``
(Python data migration), scanned from this directory and applied in number
order. Every applied file is recorded in ``schema_version`` with a SHA256
checksum over normalized (LF) bytes, so an edited migration that already ran
is caught on the next startup.

A Python data migration must expose ``def migrate(conn: sqlite3.Connection)``
and be safe to run again; the runner records it so a passing run never repeats.
"""
import hashlib
import importlib.util
import logging
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent
_MIGRATION_RE = re.compile(r"^(\d{4})_(.+)\.(sql|py)$")

BACKUP_KEEP_DEFAULT = 5
BUSY_TIMEOUT_MS = 5000


class MigrationError(Exception):
    """Base error for a failed migration run."""


class MigrationDriftError(MigrationError):
    """An already applied migration file changed on disk."""


class MigrationBackupError(MigrationError):
    """The pre migrate backup could not be written or verified."""


def _allow_drift() -> bool:
    return os.environ.get("PFA_ALLOW_MIGRATION_DRIFT", "") == "1"


def _backup_keep() -> int:
    try:
        return max(0, int(os.environ.get("PFA_BACKUP_KEEP", str(BACKUP_KEEP_DEFAULT))))
    except ValueError:
        return BACKUP_KEEP_DEFAULT


def _normalized_checksum(path: Path) -> str:
    """SHA256 over normalized (LF) line endings so CRLF changes do not trip it."""
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


def _ensure_schema_version_table(conn: sqlite3.Connection) -> None:
    """Create or extend schema_version to one row per applied migration."""
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_version "
        "(version INTEGER NOT NULL, checksum TEXT, applied_at TEXT);"
    )
    cols = {row[1] for row in conn.execute("PRAGMA table_info(schema_version)")}
    if "checksum" not in cols:
        conn.execute("ALTER TABLE schema_version ADD COLUMN checksum TEXT")
    if "applied_at" not in cols:
        conn.execute("ALTER TABLE schema_version ADD COLUMN applied_at TEXT")
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ux_schema_version_version "
        "ON schema_version(version);"
    )


def _read_applied(conn: sqlite3.Connection) -> dict[int, Optional[str]]:
    return {int(r[0]): r[1] for r in conn.execute("SELECT version, checksum FROM schema_version")}


def get_current_version(conn: sqlite3.Connection) -> int:
    """Return the highest applied schema version, or 0 for a fresh database."""
    _ensure_schema_version_table(conn)
    row = conn.execute("SELECT MAX(version) FROM schema_version").fetchone()
    return int(row[0]) if row and row[0] is not None else 0


def get_available_migrations(
    migrations_dir: Optional[Path] = None,
) -> list[tuple[int, str, Path]]:
    """Scan for NNNN_name.sql and NNNN_name.py files, sorted by version.

    Duplicate version numbers are rejected.
    """
    target_dir = migrations_dir or MIGRATIONS_DIR
    migrations: list[tuple[int, str, Path]] = []
    if target_dir.exists():
        for file_path in sorted(target_dir.iterdir()):
            match = _MIGRATION_RE.match(file_path.name)
            if match:
                migrations.append((int(match.group(1)), match.group(2), file_path))
    migrations.sort(key=lambda m: m[0])

    seen: dict[int, Path] = {}
    for version, _name, path in migrations:
        if version in seen:
            raise MigrationError(
                f"duplicate migration version {version:04d}: "
                f"{seen[version].name} and {path.name}"
            )
        seen[version] = path
    return migrations


def _iter_statements(sql: str) -> list[str]:
    """Split a SQL file into single statements, honoring strings and triggers."""
    statements: list[str] = []
    buf = ""
    for ch in sql:
        buf += ch
        if ch == ";" and sqlite3.complete_statement(buf):
            stmt = buf.strip()
            if stmt:
                statements.append(stmt)
            buf = ""
    if buf.strip():
        raise MigrationError("unterminated SQL statement (missing ';') at end of migration file")
    return statements


def _main_db_path(conn: sqlite3.Connection) -> Optional[Path]:
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main":
            return Path(row[2]) if row[2] else None
    return None


def backup_database(
    db_path: Path | str,
    version: int,
    backup_dir: Optional[Path | str] = None,
    keep: Optional[int] = None,
) -> Path:
    """Write a verified pre migrate backup; fail closed on any error."""
    db_path = Path(db_path)
    backup_dir = Path(backup_dir) if backup_dir is not None else db_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    keep = _backup_keep() if keep is None else keep

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{db_path.stem}_{version}_{timestamp}.db"

    src = sqlite3.connect(str(db_path))
    try:
        dest_conn = sqlite3.connect(str(dest))
        try:
            src.backup(dest_conn)
        finally:
            dest_conn.close()
    except Exception as exc:  # noqa: BLE001 - fail closed on any backup error
        try:
            dest.unlink()
        except OSError:
            pass
        raise MigrationBackupError(f"pre-migration backup failed for {db_path}: {exc}") from exc
    finally:
        src.close()

    check = sqlite3.connect(str(dest))
    try:
        row = check.execute("PRAGMA integrity_check").fetchone()
        result = row[0] if row else ""
    finally:
        check.close()
    if result != "ok":
        try:
            dest.unlink()
        except OSError:
            pass
        raise MigrationBackupError(f"backup integrity check failed for {dest}: {result}")

    prune_backups(backup_dir, keep)
    return dest


def prune_backups(backup_dir: Path | str, keep: int) -> list[Path]:
    """Remove the oldest backups, keeping the newest ``keep`` files."""
    backup_dir = Path(backup_dir)
    if not backup_dir.exists():
        return []
    backups = sorted(
        (p for p in backup_dir.glob("*.db") if p.is_file()),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    removed: list[Path] = []
    for path in backups[max(keep, 0):]:
        try:
            path.unlink()
            removed.append(path)
        except OSError:
            logger.warning("could not prune backup %s", path)
    return removed


def _adopt_trust_on_first_use(
    conn: sqlite3.Connection,
    available: list[tuple[int, str, Path]],
    applied: dict[int, Optional[str]],
) -> None:
    """Adopt rows written before checksums existed, computing their hash now."""
    if not applied:
        return
    max_recorded = max(applied)
    for version, _name, path in available:
        if version <= max_recorded and version not in applied:
            conn.execute(
                "INSERT OR IGNORE INTO schema_version (version, checksum, applied_at) "
                "VALUES (?, ?, NULL);",
                (version, _normalized_checksum(path)),
            )
            applied[version] = _normalized_checksum(path)
        elif applied.get(version) is None:
            checksum = _normalized_checksum(path)
            conn.execute(
                "UPDATE schema_version SET checksum = ? WHERE version = ?;",
                (checksum, version),
            )
            applied[version] = checksum


def _verify_checksums(
    available: list[tuple[int, str, Path]],
    applied: dict[int, Optional[str]],
) -> None:
    for version, _name, path in available:
        stored = applied.get(version)
        if stored is None:
            continue
        actual = _normalized_checksum(path)
        if actual != stored and not _allow_drift():
            raise MigrationDriftError(
                f"Migration {path.name} (version {version:04d}) changed after it was "
                f"applied. Refusing to start so data is not put at risk. Restore the "
                f"file, or set PFA_ALLOW_MIGRATION_DRIFT=1 to override."
            )


def _apply_migration(conn: sqlite3.Connection, version: int, name: str, path: Path) -> None:
    if path.suffix == ".py":
        module_name = f"pfa_migration_{version:04d}_{name}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise MigrationError(f"could not load Python migration {path.name}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        migrate_fn = getattr(module, "migrate", None)
        if not callable(migrate_fn):
            raise MigrationError(
                f"Python migration {path.name} must define a callable migrate(conn)"
            )
        migrate_fn(conn)
    else:
        sql = path.read_text(encoding="utf-8")
        for statement in _iter_statements(sql):
            conn.execute(statement)


def run_migrations(
    conn: sqlite3.Connection,
    migrations_dir: Optional[Path] = None,
) -> list[int]:
    """Apply pending migrations inside a single explicit transaction.

    Locks with ``BEGIN IMMEDIATE`` and re checks the applied set inside the
    lock, so two concurrent startups cannot race. A failure rolls back the
    whole run and raises ``MigrationError``.
    """
    available = get_available_migrations(migrations_dir)

    original_isolation = conn.isolation_level
    conn.isolation_level = None
    executed: list[int] = []
    try:
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN IMMEDIATE")
        try:
            _ensure_schema_version_table(conn)
            applied = _read_applied(conn)
            _adopt_trust_on_first_use(conn, available, applied)
            applied = _read_applied(conn)
            _verify_checksums(available, applied)

            pending = [(v, n, p) for v, n, p in available if v not in applied]
            if not pending:
                conn.execute("COMMIT")
                return []

            if applied:
                db_path = _main_db_path(conn)
                if db_path is not None and db_path.exists():
                    backup_database(db_path, max(applied))

            for version, name, path in pending:
                try:
                    _apply_migration(conn, version, name, path)
                except MigrationError:
                    raise
                except Exception as exc:  # noqa: BLE001 - wrap for a clear message
                    raise MigrationError(
                        f"migration {path.name} (version {version:04d}) failed: {exc}"
                    ) from exc
                conn.execute(
                    "INSERT INTO schema_version (version, checksum, applied_at) VALUES (?, ?, ?);",
                    (version, _normalized_checksum(path), datetime.now(timezone.utc).isoformat()),
                )
                executed.append(version)

            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
    finally:
        conn.isolation_level = original_isolation

    return executed
