import os
import unittest

from larder import store

from .helpers import TODAY, run_cli, scratch_dir


class CliTests(unittest.TestCase):
    def setUp(self):
        self._scratch = scratch_dir()
        self.dir = self._scratch.__enter__()
        self.path = os.path.join(self.dir, "pantry.json")

    def tearDown(self):
        self._scratch.__exit__(None, None, None)

    def run_with_file(self, *argv):
        return run_cli("--file", self.path, "--today", TODAY, *argv)

    def test_add_creates_file_and_confirms(self):
        code, out, _ = self.run_with_file("add", "Greek yogurt", "2", "2026-10-22", "--category", "Dairy")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "Added 2 pcs of Greek yogurt (expires 2026-10-22)")
        self.assertEqual(store.load(self.path)[0].category, "Dairy")

    def test_add_twice_merges_into_one_line(self):
        self.run_with_file("add", "Eggs", "6", "2026-11-01")
        self.run_with_file("add", "eggs", "6", "2026-11-01")
        self.assertEqual([i.quantity for i in store.load(self.path)], [12])

    def test_list_shows_status_relative_to_today(self):
        self.run_with_file("add", "Milk", "1", "2026-10-10")
        self.run_with_file("add", "Rice", "1", "2026-10-17")
        self.run_with_file("add", "Pasta", "1", "2026-10-27")
        _, out, _ = self.run_with_file("list")
        self.assertIn("expired 7d ago", out)
        self.assertIn("expires today", out)
        self.assertIn("in 10d", out)

    def test_empty_pantry_messages(self):
        _, out, _ = self.run_with_file("list")
        self.assertEqual(out.strip(), "Pantry is empty.")
        _, out, _ = self.run_with_file("stats")
        self.assertEqual(out.strip(), "Pantry is empty.")

    def test_use_reports_plan_and_saves_remaining_stock(self):
        self.run_with_file("add", "Yogurt", "2", "2026-10-20")
        self.run_with_file("add", "Yogurt", "3", "2026-10-30")
        code, out, _ = self.run_with_file("use", "Yogurt", "4")
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "Used 4 of Yogurt (2 from 2026-10-20, 2 from 2026-10-30)")
        remaining = [(i.expires.isoformat(), i.quantity) for i in store.load(self.path)]
        self.assertEqual(remaining, [("2026-10-30", 1)])

    def test_use_too_much_fails_with_exit_1_and_keeps_file(self):
        self.run_with_file("add", "Yogurt", "2", "2026-10-20")
        code, out, err = self.run_with_file("use", "Yogurt", "9")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("larder: error: only 2 pcs of Yogurt", err)
        self.assertEqual(store.load(self.path)[0].quantity, 2)

    def test_use_refuses_expired_only_stock(self):
        self.run_with_file("add", "Yogurt", "2", "2026-10-10")
        code, _, err = self.run_with_file("use", "Yogurt", "1")
        self.assertEqual(code, 1)
        self.assertIn("has expired", err)
        self.assertEqual(store.load(self.path)[0].quantity, 2)

    def test_directory_as_file_is_reported_not_raised(self):
        code, _, err = run_cli("--file", self.dir, "--today", TODAY, "list")
        self.assertEqual(code, 1)
        self.assertIn("larder: error:", err)

    def test_non_utf8_file_is_reported_not_raised(self):
        with open(self.path, "wb") as handle:
            handle.write(b"\xff\xfe\x00 not text")
        code, _, err = self.run_with_file("list")
        self.assertEqual(code, 1)
        self.assertIn("is not UTF-8 text", err)

    def test_expiring_and_expired_commands(self):
        self.run_with_file("add", "Milk", "1", "2026-10-16")
        self.run_with_file("add", "Cheese", "1", "2026-10-20")
        self.run_with_file("add", "Pasta", "1", "2027-06-01")
        _, out, _ = self.run_with_file("expiring")
        self.assertIn("Cheese", out)
        self.assertNotIn("Pasta", out)
        self.assertNotIn("Milk", out)
        _, out, _ = self.run_with_file("expired")
        self.assertIn("Milk", out)
        self.assertNotIn("Cheese", out)

    def test_shopping_list_uses_unexpired_stock_only(self):
        self.run_with_file("add", "Rice", "2", "2026-12-01", "--unit", "kg", "--min", "5")
        self.run_with_file("add", "Rice", "10", "2026-10-01", "--unit", "kg", "--min", "5")
        _, out, _ = self.run_with_file("shopping")
        self.assertIn("3", out)
        self.assertIn("have 2, minimum 5", out)
        _, low, _ = self.run_with_file("low")
        self.assertIn("MINIMUM", low)

    def test_remove_by_name_and_expiry(self):
        self.run_with_file("add", "Milk", "1", "2026-10-20")
        self.run_with_file("add", "Milk", "1", "2026-10-25")
        _, out, _ = self.run_with_file("remove", "Milk", "--expires", "2026-10-25")
        self.assertEqual(out.strip(), "Removed 1 line(s) for Milk")
        self.assertEqual([i.expires.isoformat() for i in store.load(self.path)], ["2026-10-20"])

    def test_remove_missing_item_is_error(self):
        code, _, err = self.run_with_file("remove", "Caviar")
        self.assertEqual(code, 1)
        self.assertIn("nothing named 'Caviar'", err)

    def test_stats_counts_per_category(self):
        self.run_with_file("add", "Milk", "1", "2026-10-10", "--category", "Dairy")
        self.run_with_file("add", "Cheese", "1", "2026-11-10", "--category", "Dairy")
        _, out, _ = self.run_with_file("stats")
        self.assertIn("Dairy", out)
        self.assertIn("Lines: 2   Expired: 1   Expiring within 7 days: 0", out)

    def test_export_prints_csv(self):
        self.run_with_file("add", "Eggs", "6", "2026-11-01")
        code, out, _ = self.run_with_file("export")
        self.assertEqual(code, 0)
        self.assertTrue(out.startswith("name,quantity,unit,category,expires,min_quantity\n"))
        self.assertIn("Eggs,6,pcs,Uncategorized,2026-11-01,0", out)

    def test_bad_quantity_is_reported_not_crashing(self):
        code, _, err = self.run_with_file("add", "Eggs", "six", "2026-11-01")
        self.assertEqual(code, 1)
        self.assertIn("quantity must be a whole number", err)
        self.assertFalse(os.path.exists(self.path))

    def test_bad_date_is_reported(self):
        code, _, err = self.run_with_file("add", "Eggs", "6", "02/11/2026")
        self.assertEqual(code, 1)
        self.assertIn("expected YYYY-MM-DD", err)

    def test_unknown_sort_is_rejected_by_argparse(self):
        self.run_with_file("add", "Eggs", "6", "2026-11-01")
        with self.assertRaises(SystemExit) as caught:
            self.run_with_file("list", "--sort", "colour")
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
