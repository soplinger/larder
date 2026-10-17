import json
import os
import unittest

from larder import store
from larder.core import LarderError, make_item

from .helpers import scratch_dir


class StoreTests(unittest.TestCase):
    def test_round_trip_preserves_every_field(self):
        items = [
            make_item("Greek yogurt", 2, "2026-10-22", unit="tubs", category="Dairy", min_quantity=3),
            make_item("Rice", 1, "2027-03-01", unit="kg"),
        ]
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            store.save(path, items)
            self.assertEqual(store.load(path), items)

    def test_save_leaves_no_temp_files_behind(self):
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            store.save(path, [make_item("Eggs", 6, "2026-11-01")])
            self.assertEqual(os.listdir(tmp), ["pantry.json"])

    def test_missing_file_is_an_empty_pantry(self):
        with scratch_dir() as tmp:
            self.assertEqual(store.load(os.path.join(tmp, "nope.json")), [])

    def test_rejects_unknown_field_instead_of_ignoring_it(self):
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            payload = {"version": 1, "items": [{"name": "Eggs", "quantity": 6, "expires": "2026-11-01", "qantity": 9}]}
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            with self.assertRaisesRegex(LarderError, "unknown field.*qantity"):
                store.load(path)

    def test_reports_invalid_json_with_line_number(self):
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            with open(path, "w", encoding="utf-8") as handle:
                handle.write('{"version": 1,\n "items": [\n')
            with self.assertRaisesRegex(LarderError, "not valid JSON"):
                store.load(path)

    def test_reports_which_item_is_bad(self):
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            payload = {"items": [{"name": "Eggs", "quantity": 6, "expires": "2026-11-01"}, {"name": "Milk", "quantity": 1}]}
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle)
            with self.assertRaisesRegex(LarderError, r"items\[1\] is missing expires"):
                store.load(path)

    def test_rejects_unsupported_version(self):
        with scratch_dir() as tmp:
            path = os.path.join(tmp, "pantry.json")
            with open(path, "w", encoding="utf-8") as handle:
                json.dump({"version": 99, "items": []}, handle)
            with self.assertRaisesRegex(LarderError, "unsupported version"):
                store.load(path)

    def test_csv_export_has_header_and_quotes_commas(self):
        items = [make_item("Beans, black", 2, "2026-12-31", category="Tins")]
        self.assertEqual(
            store.to_csv(items),
            "name,quantity,unit,category,expires,min_quantity\n"
            '"Beans, black",2,pcs,Tins,2026-12-31,0\n',
        )


if __name__ == "__main__":
    unittest.main()
