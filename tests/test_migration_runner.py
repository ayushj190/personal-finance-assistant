import hashlib
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from db.database import connect, migrate, upsert_account, upsert_holdings, upsert_market_quotes, upsert_transactions
from db.migrations.runner import (
    MigrationDriftError,
    MigrationError,
    backup_database,
    get_available_migrations,
    get_current_version,
    prune_backups,
    run_migrations,
)

SQL_CREATE = "CREATE TABLE thing (id INTEGER PRIMARY KEY, v TEXT);\n"


def _lf_sha256(path: Path) -> str:
    data = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    return hashlib.sha256(data).hexdigest()


class TestMigrationRunner(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.migrations = self.dir / "migrations"
        self.migrations.mkdir()
        self.db_path = self.dir / "app.db"

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name: str, content: str) -> Path:
        path = self.migrations / name
        path.write_text(content, encoding="utf-8")
        return path

    def _conn(self) -> sqlite3.Connection:
        return connect(self.db_path)

    def test_checksum_recorded_and_idempotent(self):
        path = self._write("0001_a.sql", SQL_CREATE)
        conn = self._conn()
        try:
            self.assertEqual(run_migrations(conn, self.migrations), [1])
            row = conn.execute(
                "SELECT version, checksum FROM schema_version WHERE version = 1"
            ).fetchone()
            self.assertEqual(row["checksum"], _lf_sha256(path))
            self.assertEqual(run_migrations(conn, self.migrations), [])
        finally:
            conn.close()

    def test_drift_detected_then_override(self):
        path = self._write("0001_a.sql", SQL_CREATE)
        conn = self._conn()
        try:
            run_migrations(conn, self.migrations)
            path.write_text(SQL_CREATE + "-- edited later\n", encoding="utf-8")
            with self.assertRaises(MigrationDriftError) as ctx:
                run_migrations(conn, self.migrations)
            self.assertIn("0001_a.sql", str(ctx.exception))
            os.environ["PFA_ALLOW_MIGRATION_DRIFT"] = "1"
            try:
                self.assertEqual(run_migrations(conn, self.migrations), [])
            finally:
                del os.environ["PFA_ALLOW_MIGRATION_DRIFT"]
        finally:
            conn.close()

    def test_legacy_row_adopted_trust_on_first_use(self):
        conn = self._conn()
        try:
            conn.execute("CREATE TABLE thing (id INTEGER PRIMARY KEY, v TEXT);")
            conn.execute("CREATE TABLE other (id INTEGER PRIMARY KEY);")
            conn.execute("CREATE TABLE schema_version (version INTEGER NOT NULL);")
            conn.execute("INSERT INTO schema_version (version) VALUES (2);")
            conn.commit()

            p1 = self._write("0001_a.sql", SQL_CREATE)
            p2 = self._write("0002_b.sql", "CREATE TABLE other (id INTEGER PRIMARY KEY);\n")

            self.assertEqual(run_migrations(conn, self.migrations), [])
            rows = dict(conn.execute("SELECT version, checksum FROM schema_version").fetchall())
            self.assertEqual(rows[1], _lf_sha256(p1))
            self.assertEqual(rows[2], _lf_sha256(p2))
        finally:
            conn.close()

    def test_failed_migration_rolls_back(self):
        self._write("0001_a.sql", "CREATE TABLE good (id INTEGER);\nTHIS IS NOT SQL;\n")
        conn = self._conn()
        try:
            with self.assertRaises(MigrationError):
                run_migrations(conn, self.migrations)
            self.assertIsNone(
                conn.execute("SELECT name FROM sqlite_master WHERE name='good'").fetchone()
            )
            self.assertEqual(get_current_version(conn), 0)
        finally:
            conn.close()

    def test_fresh_database_skips_backup(self):
        self._write("0001_a.sql", SQL_CREATE)
        conn = self._conn()
        try:
            run_migrations(conn, self.migrations)
        finally:
            conn.close()
        self.assertFalse((self.dir / "backups").exists())

    def test_backup_written_before_pending_migration(self):
        self._write("0001_a.sql", SQL_CREATE)
        conn = self._conn()
        try:
            run_migrations(conn, self.migrations)
            with conn:
                conn.execute("INSERT INTO thing (v) VALUES ('keep me')")
            self._write("0002_b.sql", "ALTER TABLE thing ADD COLUMN extra TEXT;\n")
            self.assertEqual(run_migrations(conn, self.migrations), [2])
        finally:
            conn.close()

        backups = list((self.dir / "backups").glob("app_1_*.db"))
        self.assertEqual(len(backups), 1)
        check = sqlite3.connect(str(backups[0]))
        try:
            self.assertEqual(check.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(check.execute("SELECT v FROM thing").fetchone()[0], "keep me")
        finally:
            check.close()

    def test_prune_backups_keeps_newest(self):
        backup_dir = self.dir / "backups"
        backup_dir.mkdir()
        paths = []
        for i in range(7):
            p = backup_dir / f"app_1_2026010{i}.db"
            p.write_text("x", encoding="utf-8")
            os.utime(p, (time.time() - (7 - i) * 10, time.time() - (7 - i) * 10))
            paths.append(p)
        removed = prune_backups(backup_dir, 5)
        self.assertEqual(len(removed), 2)
        remaining = sorted(p.name for p in backup_dir.glob("*.db"))
        self.assertEqual(len(remaining), 5)
        self.assertNotIn(paths[0].name, remaining)

    def test_python_data_migration_runs_once(self):
        self._write("0001_a.sql", "CREATE TABLE t (id INTEGER PRIMARY KEY, v TEXT);\n")
        self._write(
            "0002_backfill.py",
            "def migrate(conn):\n    conn.execute(\"INSERT INTO t (v) VALUES ('x')\")\n",
        )
        conn = self._conn()
        try:
            self.assertEqual(run_migrations(conn, self.migrations), [1, 2])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
            self.assertEqual(run_migrations(conn, self.migrations), [])
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM t").fetchone()[0], 1)
        finally:
            conn.close()

    def test_python_migration_without_migrate_is_rejected(self):
        self._write("0001_a.py", "x = 1\n")
        conn = self._conn()
        try:
            with self.assertRaises(MigrationError):
                run_migrations(conn, self.migrations)
        finally:
            conn.close()

    def test_duplicate_version_rejected(self):
        self._write("0001_a.sql", SQL_CREATE)
        self._write("0001_b.sql", SQL_CREATE)
        with self.assertRaises(MigrationError):
            get_available_migrations(self.migrations)

    def test_backup_database_direct(self):
        conn = self._conn()
        try:
            run_migrations(conn, self.migrations)
        finally:
            conn.close()
        self._write("0001_a.sql", SQL_CREATE)
        dest = backup_database(self.db_path, 0, keep=2)
        self.assertTrue(dest.exists())
        self.assertEqual(dest.parent.name, "backups")


class TestIdempotentIngest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.tmp.name, "finance.db")
        migrate(self.db_path)
        self.conn = connect(self.db_path)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_repeated_sync_inserts_no_duplicate_transactions(self):
        acc_id = upsert_account(self.conn, {
            "provider": "manual", "institution": "ABN", "name": "Checking",
            "currency": "EUR", "asset_class": "cash", "external_id": "sync_acc",
        })
        tx = {
            "account_id": acc_id, "dedup_hash": "sync_hash_1",
            "booking_date": "2026-03-01", "amount_minor": -350, "currency": "EUR",
            "amount_eur_minor": -350, "description_raw": "Coffee", "source": "csv",
        }
        self.assertEqual(upsert_transactions(self.conn, [tx]), 1)
        self.assertEqual(upsert_transactions(self.conn, [tx]), 0)
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0], 1
        )

    def test_repeated_sync_holdings_and_quotes_idempotent(self):
        acc_id = upsert_account(self.conn, {
            "provider": "etoro", "institution": "eToro", "name": "eToro",
            "currency": "USD", "asset_class": "investment", "external_id": "etoro_sync",
        })
        holding = {
            "account_id": acc_id, "ticker": "AAPL", "quantity": 3.0,
            "cost_basis_minor": 100000, "currency": "USD", "updated_at": "2026-10-01",
        }
        quote = {"ticker": "AAPL", "quote_date": "2026-10-01", "close": 200.0, "prev_close": 199.0, "currency": "USD"}
        upsert_holdings(self.conn, [holding])
        upsert_market_quotes(self.conn, [quote])
        upsert_holdings(self.conn, [holding])
        upsert_market_quotes(self.conn, [quote])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM holdings WHERE ticker = 'AAPL'").fetchone()[0], 1
        )
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM market_quotes WHERE ticker = 'AAPL'").fetchone()[0], 1
        )


if __name__ == "__main__":
    unittest.main()
