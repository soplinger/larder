"""Command-line interface. Each subcommand is a thin wrapper around core/store."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from . import __version__, core, store
from .core import LarderError, parse_date

DEFAULT_FILE = "larder.json"
EXPIRING_WINDOW_DAYS = 7


def _status(days: int) -> str:
    if days < 0:
        return f"expired {-days}d ago"
    if days == 0:
        return "expires today"
    return f"in {days}d"


def render_table(headers: list[str], rows: list[list[object]]) -> str:
    """Left-aligned plain-text table with a header underline."""
    cells = [[str(c) for c in row] for row in rows]
    widths = [len(h) for h in headers]
    for row in cells:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def line(values: list[str]) -> str:
        return "  ".join(v.ljust(widths[i]) for i, v in enumerate(values)).rstrip()

    out = [line(headers), line(["-" * w for w in widths])]
    out.extend(line(row) for row in cells)
    return "\n".join(out)


def _int(text: str, field: str) -> int:
    try:
        return int(text)
    except ValueError:
        raise LarderError(f"{field} must be a whole number, got {text!r}") from None


def _item_rows(items: list[core.Item], today: date) -> list[list[object]]:
    return [
        [i.name, i.quantity, i.unit, i.category, i.expires.isoformat(), _status(core.days_until(i, today))]
        for i in items
    ]


ITEM_HEADERS = ["NAME", "QTY", "UNIT", "CATEGORY", "EXPIRES", "STATUS"]


def cmd_add(args, items, today):
    new = core.make_item(
        args.name,
        _int(args.quantity, "quantity"),
        args.expires,
        unit=args.unit,
        category=args.category,
        min_quantity=_int(args.min, "min"),
    )
    items = core.add_item(items, new)
    print(f"Added {new.quantity} {new.unit} of {new.name} (expires {new.expires.isoformat()})")
    return items, True


def cmd_list(args, items, today):
    shown = core.sort_items(items, args.sort)
    if args.category:
        shown = [i for i in shown if i.category.casefold() == args.category.casefold()]
    if not shown:
        print("Pantry is empty." if not items else "No items match.")
    else:
        print(render_table(ITEM_HEADERS, _item_rows(shown, today)))
    return items, False


def cmd_expiring(args, items, today):
    found = core.expiring_soon(items, today, args.days)
    if not found:
        print(f"Nothing expires in the next {args.days} day(s).")
    else:
        print(render_table(ITEM_HEADERS, _item_rows(found, today)))
    return items, False


def cmd_expired(args, items, today):
    found = core.expired(items, today)
    if not found:
        print("Nothing has expired.")
    else:
        print(render_table(ITEM_HEADERS, _item_rows(found, today)))
    return items, False


def cmd_use(args, items, today):
    amount = _int(args.amount, "amount")
    items, plan = core.consume(items, args.name, amount, today, unit=args.unit)
    parts = ", ".join(f"{taken} from {line.expires.isoformat()}" for line, taken in plan)
    print(f"Used {amount} of {args.name} ({parts})")
    return items, True


def cmd_remove(args, items, today):
    expires = parse_date(args.expires) if args.expires else None
    items, removed = core.remove(items, args.name, expires)
    print(f"Removed {removed} line(s) for {args.name}")
    return items, True


def cmd_low(args, items, today):
    short = core.shortfalls(items, today)
    if not short:
        print("Every item with a minimum is at or above it.")
    else:
        rows = [[s.name, s.unit, s.have, s.minimum] for s in short]
        print(render_table(["NAME", "UNIT", "HAVE", "MINIMUM"], rows))
    return items, False


def cmd_shopping(args, items, today):
    short = core.shortfalls(items, today)
    if not short:
        print("Nothing to buy.")
    else:
        rows = [[s.name, s.short_by, s.unit, f"have {s.have}, minimum {s.minimum}"] for s in short]
        print(render_table(["ITEM", "AMOUNT", "UNIT", "NOTE"], rows))
    return items, False


def cmd_stats(args, items, today):
    if not items:
        print("Pantry is empty.")
        return items, False
    totals = core.category_totals(items, today)
    expiring = core.expiring_soon(items, today, EXPIRING_WINDOW_DAYS)
    rows = [[c, t["lines"], t["expired"]] for c, t in totals.items()]
    print(render_table(["CATEGORY", "LINES", "EXPIRED"], rows))
    print()
    print(f"Lines: {len(items)}   Expired: {len(core.expired(items, today))}"
          f"   Expiring within {EXPIRING_WINDOW_DAYS} days: {len(expiring)}")
    return items, False


def cmd_export(args, items, today):
    sys.stdout.write(store.to_csv(items))
    return items, False


COMMANDS = {
    "add": cmd_add,
    "list": cmd_list,
    "expiring": cmd_expiring,
    "expired": cmd_expired,
    "use": cmd_use,
    "remove": cmd_remove,
    "low": cmd_low,
    "shopping": cmd_shopping,
    "stats": cmd_stats,
    "export": cmd_export,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="larder",
        description="Track pantry stock, expiry dates and restock needs.",
    )
    parser.add_argument("--version", action="version", version=f"larder {__version__}")
    parser.add_argument(
        "--file",
        default=os.environ.get("LARDER_FILE", DEFAULT_FILE),
        help=f"pantry JSON file (default: $LARDER_FILE or {DEFAULT_FILE})",
    )
    parser.add_argument(
        "--today",
        default=None,
        help="pretend today is YYYY-MM-DD (useful for planning and tests)",
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    add = sub.add_parser("add", help="add stock")
    add.add_argument("name")
    add.add_argument("quantity", help="whole number, at least 1")
    add.add_argument("expires", help="expiry date, YYYY-MM-DD")
    add.add_argument("--unit", default=core.DEFAULT_UNIT)
    add.add_argument("--category", default=core.DEFAULT_CATEGORY)
    add.add_argument("--min", default="0", help="minimum stock to keep on hand")

    lst = sub.add_parser("list", help="show all stock")
    lst.add_argument("--sort", default="expires", choices=["expires", "name", "category", "quantity"])
    lst.add_argument("--category", default=None, help="only show this category")

    exp = sub.add_parser("expiring", help="show stock expiring soon")
    exp.add_argument("--days", type=int, default=EXPIRING_WINDOW_DAYS)

    sub.add_parser("expired", help="show stock already past its date")

    use = sub.add_parser("use", help="use stock, soonest-expiring first")
    use.add_argument("name")
    use.add_argument("amount")
    use.add_argument("--unit", default=None, help="needed if the name has several units")

    rem = sub.add_parser("remove", help="throw stock away")
    rem.add_argument("name")
    rem.add_argument("--expires", default=None, help="only remove the line expiring on this date")

    sub.add_parser("low", help="show items below their minimum stock")
    sub.add_parser("shopping", help="show how much to buy to reach minimum stock")
    sub.add_parser("stats", help="summarise by category")
    sub.add_parser("export", help="print the pantry as CSV")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        today = parse_date(args.today) if args.today else date.today()
        items = store.load(args.file)
        items, changed = COMMANDS[args.command](args, items, today)
        if changed:
            store.save(args.file, items)
    except (LarderError, OSError) as exc:
        print(f"larder: error: {exc}", file=sys.stderr)
        return 1
    return 0
