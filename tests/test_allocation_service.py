import tempfile
import unittest
from pathlib import Path

from db import database
from db.migrations.runner import run_migrations
from services import allocation_service as alloc


class TestAllocationService(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = Path(tempfile.mkdtemp())
        self.conn = database.connect(self.tmp_dir / "alloc_test.db")
        run_migrations(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_no_seeded_defaults_remain(self):
        # The old 80/20 Core-Satellite starter profiles are gone for good.
        self.assertEqual(alloc.list_allocation_profiles(self.conn), [])

    def test_nature_dimension_buckets(self):
        buckets = alloc.get_valid_buckets(self.conn, "nature")
        self.assertIn("Equities", buckets)
        self.assertIn("Fixed Income", buckets)
        self.assertIn("Digital Assets (Crypto)", buckets)

    def test_create_then_delete_with_token(self):
        alloc.create_allocation_profile(self.conn, "Keeper", "nature", {"Equities": 100.0})
        res = alloc.create_allocation_profile(
            self.conn, "My 70/30", "nature", {"Equities": 70.0, "Fixed Income": 30.0}
        )
        self.assertTrue(res["success"])
        self.assertFalse(res["profile"]["is_active"])

        first = alloc.delete_allocation_profile(self.conn, "my 70/30")
        self.assertTrue(first.get("requires_confirmation"))
        token = first["confirm_token"]

        wrong = alloc.delete_allocation_profile(self.conn, "My 70/30", "not-the-token")
        self.assertTrue(wrong.get("requires_confirmation"))

        done = alloc.delete_allocation_profile(self.conn, "my 70/30", token)
        self.assertTrue(done["success"])
        names = [p["name"] for p in alloc.list_allocation_profiles(self.conn)]
        self.assertNotIn("My 70/30", names)

    def test_create_validation_writes_nothing(self):
        self.assertFalse(alloc.create_allocation_profile(self.conn, "", "nature", {"Equities": 100.0})["success"])
        self.assertFalse(alloc.create_allocation_profile(self.conn, "X", "bogus", {"Equities": 100.0})["success"])
        # asset_type (stock vs ETF) is no longer an accepted dimension.
        self.assertFalse(alloc.create_allocation_profile(self.conn, "X", "asset_type", {"etf": 100.0})["success"])

        bad_sum = alloc.create_allocation_profile(self.conn, "X", "nature", {"Equities": 90.0})
        self.assertFalse(bad_sum["success"])
        self.assertIn("90.0", bad_sum["message"])

        bad_bucket = alloc.create_allocation_profile(self.conn, "X", "nature", {"nope": 100.0})
        self.assertFalse(bad_bucket["success"])
        self.assertIn("nope", bad_bucket["message"])

        names = [p["name"] for p in alloc.list_allocation_profiles(self.conn)]
        self.assertNotIn("X", names)

        alloc.create_allocation_profile(self.conn, "Dup", "nature", {"Equities": 100.0})
        dup = alloc.create_allocation_profile(self.conn, "dup", "nature", {"Equities": 100.0})
        self.assertFalse(dup["success"])

    def test_delete_refuses_active_and_last_remaining(self):
        alloc.create_allocation_profile(self.conn, "A", "nature", {"Equities": 100.0})
        alloc.create_allocation_profile(self.conn, "B", "nature", {"Fixed Income": 100.0})
        with self.conn:
            self.conn.execute("UPDATE allocation_profiles SET is_active = 0")
            self.conn.execute("UPDATE allocation_profiles SET is_active = 1 WHERE name = 'A'")

        refused = alloc.delete_allocation_profile(self.conn, "A")
        self.assertFalse(refused["success"])
        self.assertNotIn("requires_confirmation", refused)
        self.assertIn("active", refused["message"])

        with self.conn:
            self.conn.execute("UPDATE allocation_profiles SET is_active = 0")

        first = alloc.delete_allocation_profile(self.conn, "B")
        alloc.delete_allocation_profile(self.conn, "B", first["confirm_token"])

        remaining = alloc.list_allocation_profiles(self.conn)
        self.assertEqual(len(remaining), 1)
        last = alloc.delete_allocation_profile(self.conn, remaining[0]["name"])
        self.assertFalse(last["success"])
        self.assertIn("last remaining", last["message"])


if __name__ == "__main__":
    unittest.main()
