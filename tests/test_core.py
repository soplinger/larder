import unittest
from datetime import date

from larder import core
from larder.core import InsufficientStockError, Item, LarderError, make_item

from .helpers import TODAY

T = date.fromisoformat(TODAY)


def line(name="Milk", qty=1, expires="2026-10-20", unit="pcs", category="Dairy", min_quantity=0):
    return make_item(name, qty, expires, unit=unit, category=category, min_quantity=min_quantity)


class ParseDateTests(unittest.TestCase):
    def test_accepts_strict_iso_date(self):
        self.assertEqual(core.parse_date("2026-10-17"), date(2026, 10, 17))

    def test_rejects_impossible_calendar_day(self):
        with self.assertRaisesRegex(LarderError, "no such calendar day"):
            core.parse_date("2026-02-30")

    def test_rejects_other_formats(self):
        for bad in ["17/10/2026", "2026-10-7", "20261017", "tomorrow", 20261017]:
            with self.subTest(value=bad), self.assertRaises(LarderError):
                core.parse_date(bad)


class MakeItemTests(unittest.TestCase):
    def test_builds_item_with_defaults(self):
        item = make_item("  Eggs ", 6, "2026-11-01")
        self.assertEqual(item.name, "Eggs")
        self.assertEqual(item.unit, "pcs")
        self.assertEqual(item.category, "Uncategorized")
        self.assertEqual(item.min_quantity, 0)

    def test_rejects_zero_quantity_and_booleans(self):
        with self.assertRaises(LarderError):
            make_item("Eggs", 0, "2026-11-01")
        with self.assertRaisesRegex(LarderError, "whole number"):
            make_item("Eggs", True, "2026-11-01")

    def test_rejects_blank_name(self):
        with self.assertRaisesRegex(LarderError, "name must be non-empty"):
            make_item("   ", 1, "2026-11-01")


class AddItemTests(unittest.TestCase):
    def test_same_name_unit_and_expiry_merge_ignoring_case(self):
        items = core.add_item([], line("Milk", 2))
        items = core.add_item(items, line("MILK", 3))
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].quantity, 5)
        self.assertEqual(items[0].name, "Milk")

    def test_different_expiry_keeps_separate_lines(self):
        items = core.add_item([], line("Milk", 2, "2026-10-20"))
        items = core.add_item(items, line("Milk", 1, "2026-10-25"))
        self.assertEqual([i.quantity for i in items], [2, 1])

    def test_different_unit_keeps_separate_lines(self):
        items = core.add_item([], line("Flour", 500, unit="g"))
        items = core.add_item(items, line("Flour", 2, unit="bags"))
        self.assertEqual(len(items), 2)


class ExpiryTests(unittest.TestCase):
    def test_expiring_today_is_not_yet_expired(self):
        item = line(expires="2026-10-17")
        self.assertEqual(core.days_until(item, T), 0)
        self.assertEqual(core.expired([item], T), [])

    def test_yesterday_is_expired(self):
        item = line(expires="2026-10-16")
        self.assertEqual(core.expired([item], T), [item])

    def test_expiring_soon_window_is_inclusive_and_sorted(self):
        items = [
            line("C", expires="2026-10-24"),  # 7 days: in
            line("A", expires="2026-10-18"),  # 1 day: in
            line("B", expires="2026-10-25"),  # 8 days: out
            line("D", expires="2026-10-10"),  # expired: out
        ]
        found = core.expiring_soon(items, T, 7)
        self.assertEqual([i.name for i in found], ["A", "C"])

    def test_negative_window_is_rejected(self):
        with self.assertRaises(LarderError):
            core.expiring_soon([], T, -1)


class ConsumeTests(unittest.TestCase):
    def test_takes_soonest_expiring_first_across_lines(self):
        items = [
            line("Yogurt", 2, "2026-10-30"),
            line("Yogurt", 3, "2026-10-20"),
        ]
        new_items, plan = core.consume(items, "yogurt", 4, T)
        self.assertEqual([(p.expires.isoformat(), n) for p, n in plan], [("2026-10-20", 3), ("2026-10-30", 1)])
        self.assertEqual([(i.expires.isoformat(), i.quantity) for i in new_items], [("2026-10-30", 1)])

    def test_emptied_lines_are_removed(self):
        items = [line("Yogurt", 2, "2026-10-20")]
        new_items, _ = core.consume(items, "Yogurt", 2, T)
        self.assertEqual(new_items, [])

    def test_insufficient_stock_raises_and_does_not_change_input(self):
        items = [line("Yogurt", 2)]
        with self.assertRaisesRegex(InsufficientStockError, "only 2 pcs"):
            core.consume(items, "Yogurt", 5, T)
        self.assertEqual(items[0].quantity, 2)

    def test_mixed_units_need_explicit_unit(self):
        items = [line("Flour", 500, unit="g"), line("Flour", 2, unit="bags")]
        with self.assertRaisesRegex(LarderError, "several units"):
            core.consume(items, "Flour", 100, T)
        new_items, plan = core.consume(items, "Flour", 100, T, unit="g")
        self.assertEqual(plan[0][0].unit, "g")
        self.assertEqual(sorted(i.quantity for i in new_items), [2, 400])

    def test_missing_name_is_insufficient(self):
        with self.assertRaisesRegex(InsufficientStockError, "no Rice"):
            core.consume([line("Milk")], "Rice", 1, T)

    def test_expired_line_is_never_charged(self):
        # The expired tub expires first, but it must be skipped entirely.
        items = [line("Yogurt", 2, "2026-10-10"), line("Yogurt", 1, "2026-10-25")]
        new_items, plan = core.consume(items, "Yogurt", 1, T)
        self.assertEqual([(p.expires.isoformat(), n) for p, n in plan], [("2026-10-25", 1)])
        self.assertEqual([(i.expires.isoformat(), i.quantity) for i in new_items], [("2026-10-10", 2)])

    def test_expired_only_stock_is_refused_with_hint(self):
        items = [line("Yogurt", 2, "2026-10-10")]
        with self.assertRaisesRegex(LarderError, "has expired.*larder remove Yogurt"):
            core.consume(items, "Yogurt", 1, T)

    def test_expired_stock_does_not_hide_fresh_shortage(self):
        items = [line("Yogurt", 2, "2026-10-10"), line("Yogurt", 1, "2026-10-25")]
        with self.assertRaisesRegex(InsufficientStockError, "only 1 pcs of Yogurt unexpired"):
            core.consume(items, "Yogurt", 3, T)


class RemoveTests(unittest.TestCase):
    def test_removes_all_lines_for_name(self):
        items = [line("Milk", expires="2026-10-20"), line("milk", expires="2026-10-25"), line("Eggs")]
        kept, removed = core.remove(items, "MILK")
        self.assertEqual(removed, 2)
        self.assertEqual([i.name for i in kept], ["Eggs"])

    def test_removes_only_the_line_on_given_date(self):
        items = [line("Milk", expires="2026-10-20"), line("Milk", expires="2026-10-25")]
        kept, removed = core.remove(items, "Milk", date(2026, 10, 25))
        self.assertEqual(removed, 1)
        self.assertEqual(kept[0].expires, date(2026, 10, 20))

    def test_unknown_name_is_an_error(self):
        with self.assertRaisesRegex(LarderError, "nothing named"):
            core.remove([line("Milk")], "Bread")


class ShortfallTests(unittest.TestCase):
    def test_expired_stock_does_not_count_toward_minimum(self):
        items = [
            line("Rice", 2, "2026-12-01", unit="kg", min_quantity=5),
            line("Rice", 10, "2026-10-01", unit="kg", min_quantity=5),  # expired
        ]
        short = core.shortfalls(items, T)
        self.assertEqual(len(short), 1)
        self.assertEqual((short[0].have, short[0].minimum, short[0].short_by), (2, 5, 3))

    def test_minimum_is_the_largest_declared_for_the_group(self):
        items = [line("Eggs", 4, "2026-11-01", min_quantity=6), line("eggs", 1, "2026-11-05", min_quantity=2)]
        short = core.shortfalls(items, T)
        self.assertEqual((short[0].have, short[0].minimum), (5, 6))

    def test_items_without_minimum_or_meeting_it_are_not_listed(self):
        items = [line("Salt", 1), line("Pasta", 3, min_quantity=3)]
        self.assertEqual(core.shortfalls(items, T), [])


class CategoryAndSortTests(unittest.TestCase):
    def test_category_totals_count_lines_and_expired(self):
        items = [
            line("Milk", category="Dairy", expires="2026-10-10"),
            line("Cheese", category="Dairy", expires="2026-11-10"),
            line("Rice", category="Grains", expires="2027-01-01"),
        ]
        totals = core.category_totals(items, T)
        self.assertEqual(totals["Dairy"], {"lines": 2, "expired": 1})
        self.assertEqual(totals["Grains"], {"lines": 1, "expired": 0})

    def test_sort_rejects_unknown_key(self):
        with self.assertRaisesRegex(LarderError, "unknown sort"):
            core.sort_items([], "colour")

    def test_sort_by_quantity_descending(self):
        items = [line("A", 1), line("B", 5), line("C", 3)]
        self.assertEqual([i.name for i in core.sort_items(items, "quantity")], ["B", "C", "A"])


if __name__ == "__main__":
    unittest.main()
