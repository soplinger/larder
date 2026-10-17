"""Pure pantry logic. Nothing here touches the disk or the clock.

Every function takes data and returns data, so the rules can be tested
directly. Dates are passed in explicitly (``today``) for the same reason.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from datetime import date

DEFAULT_UNIT = "pcs"
DEFAULT_CATEGORY = "Uncategorized"

_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class LarderError(ValueError):
    """A problem the user can fix: bad input, bad file, or bad request."""


class InsufficientStockError(LarderError):
    """Raised when a request would use more stock than exists."""


@dataclass(frozen=True)
class Item:
    """One pantry line: a quantity of one thing, in one unit, with one expiry date."""

    name: str
    quantity: int
    expires: date
    unit: str = DEFAULT_UNIT
    category: str = DEFAULT_CATEGORY
    min_quantity: int = 0


@dataclass(frozen=True)
class Shortfall:
    """Stock for a (name, unit) pair that sits below its minimum."""

    name: str
    unit: str
    have: int
    minimum: int

    @property
    def short_by(self) -> int:
        return self.minimum - self.have


def parse_date(value: object) -> date:
    """Parse a strict ``YYYY-MM-DD`` string. Dates pass through unchanged."""
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not _ISO_DATE.fullmatch(value.strip()):
        raise LarderError(f"invalid date {value!r}; expected YYYY-MM-DD")
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        raise LarderError(f"invalid date {value!r}; no such calendar day") from None


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LarderError(f"{field} must be non-empty text")
    return value.strip()


def _whole(value: object, field: str, minimum: int) -> int:
    # bool is a subclass of int, so reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, int):
        raise LarderError(f"{field} must be a whole number, got {value!r}")
    if value < minimum:
        raise LarderError(f"{field} must be at least {minimum}, got {value}")
    return value


def make_item(
    name: object,
    quantity: object,
    expires: object,
    unit: object = DEFAULT_UNIT,
    category: object = DEFAULT_CATEGORY,
    min_quantity: object = 0,
) -> Item:
    """Validate raw values and build an Item. Quantity must be at least 1."""
    return Item(
        name=_text(name, "name"),
        quantity=_whole(quantity, "quantity", 1),
        expires=parse_date(expires),
        unit=_text(unit, "unit"),
        category=_text(category, "category"),
        min_quantity=_whole(min_quantity, "min_quantity", 0),
    )


def _key(item: Item) -> tuple[str, str, date]:
    # Two lines are the same stock when name and unit match ignoring case,
    # and they expire on the same day.
    return (item.name.casefold(), item.unit.casefold(), item.expires)


def add_item(items: list[Item], new: Item) -> list[Item]:
    """Add stock. A line with the same name, unit and expiry is merged by summing quantities."""
    for index, existing in enumerate(items):
        if _key(existing) == _key(new):
            merged = replace(
                existing,
                quantity=existing.quantity + new.quantity,
                min_quantity=max(existing.min_quantity, new.min_quantity),
            )
            return items[:index] + [merged] + items[index + 1 :]
    return items + [new]


def days_until(item: Item, today: date) -> int:
    """Days until expiry. Zero means it expires today, negative means already expired."""
    return (item.expires - today).days


def expired(items: list[Item], today: date) -> list[Item]:
    """Lines already past their expiry date, soonest first."""
    return sorted((i for i in items if days_until(i, today) < 0), key=lambda i: i.expires)


def expiring_soon(items: list[Item], today: date, within_days: int) -> list[Item]:
    """Lines that expire today or within the next ``within_days`` days, soonest first."""
    _whole(within_days, "within_days", 0)
    return sorted(
        (i for i in items if 0 <= days_until(i, today) <= within_days),
        key=lambda i: i.expires,
    )


def consume(
    items: list[Item],
    name: str,
    amount: int,
    today: date,
    unit: str | None = None,
) -> tuple[list[Item], list[tuple[Item, int]]]:
    """Use ``amount`` of ``name``, taking the soonest-expiring stock first (FIFO by expiry).

    Expired lines are never used; ``shortfalls`` treats them the same way.
    Returns the new pantry and a plan of ``(line, taken)`` pairs. Nothing is
    changed if there is not enough unexpired stock. If the name is stored in
    more than one unit and no ``unit`` is given, this refuses to guess,
    because mixing grams with pieces would be silently wrong.
    """
    _whole(amount, "amount", 1)
    wanted = _text(name, "name").casefold()
    wanted_unit = unit.strip().casefold() if unit is not None else None

    # Track matches by list position, not by value, so duplicate lines in a
    # hand-edited file are each charged correctly.
    named = [
        n
        for n, i in enumerate(items)
        if i.name.casefold() == wanted and (wanted_unit is None or i.unit.casefold() == wanted_unit)
    ]
    if not named:
        raise InsufficientStockError(f"no {name} in stock")

    matches = [n for n in named if days_until(items[n], today) >= 0]
    if not matches:
        raise LarderError(f"every {name} line has expired; clear them with 'larder remove {name}'")

    units = sorted({items[n].unit for n in matches})
    if len(units) > 1:
        raise LarderError(f"{name} is stored in several units ({', '.join(units)}); pass --unit")

    total = sum(items[n].quantity for n in matches)
    if total < amount:
        raise InsufficientStockError(
            f"only {total} {units[0]} of {name} unexpired in stock, cannot use {amount}"
        )

    usage: dict[int, int] = {}
    plan: list[tuple[Item, int]] = []
    remaining = amount
    for index in sorted(matches, key=lambda n: items[n].expires):
        if remaining == 0:
            break
        taken = min(items[index].quantity, remaining)
        usage[index] = taken
        plan.append((items[index], taken))
        remaining -= taken

    new_items = []
    for index, line in enumerate(items):
        left = line.quantity - usage.get(index, 0)
        if left > 0:
            new_items.append(replace(line, quantity=left))
    return new_items, plan


def remove(items: list[Item], name: str, expires: date | None = None) -> tuple[list[Item], int]:
    """Drop every line for ``name``, or only the line expiring on ``expires``. Returns the count removed."""
    wanted = _text(name, "name").casefold()
    kept = []
    removed = 0
    for line in items:
        matches = line.name.casefold() == wanted and (expires is None or line.expires == expires)
        if matches:
            removed += 1
        else:
            kept.append(line)
    if removed == 0:
        raise LarderError(f"nothing named {name!r} to remove")
    return kept, removed


def shortfalls(items: list[Item], today: date) -> list[Shortfall]:
    """Compare unexpired stock with each item's minimum, per (name, unit).

    The minimum for a group is the largest ``min_quantity`` among its lines.
    Expired stock is not counted, because you cannot cook with it.
    Only groups below their minimum are returned, sorted by name.
    """
    groups: dict[tuple[str, str], dict] = {}
    for line in items:
        group = groups.setdefault(
            (line.name.casefold(), line.unit.casefold()),
            {"name": line.name, "unit": line.unit, "have": 0, "minimum": 0},
        )
        group["minimum"] = max(group["minimum"], line.min_quantity)
        if days_until(line, today) >= 0:
            group["have"] += line.quantity

    result = [
        Shortfall(g["name"], g["unit"], g["have"], g["minimum"])
        for g in groups.values()
        if g["minimum"] > 0 and g["have"] < g["minimum"]
    ]
    return sorted(result, key=lambda s: (s.name.casefold(), s.unit.casefold()))


def category_totals(items: list[Item], today: date) -> dict[str, dict[str, int]]:
    """Per category: line count and expired line count.

    Categories match ignoring case; the first spelling seen is the display name.
    Quantities are not summed here because lines may use different units.
    """
    totals: dict[str, dict[str, int]] = {}
    display: dict[str, str] = {}
    for line in sorted(items, key=lambda i: i.category.casefold()):
        name = display.setdefault(line.category.casefold(), line.category)
        row = totals.setdefault(name, {"lines": 0, "expired": 0})
        row["lines"] += 1
        if days_until(line, today) < 0:
            row["expired"] += 1
    return totals


def sort_items(items: list[Item], by: str) -> list[Item]:
    """Sort by ``expires``, ``name``, ``category`` or ``quantity``."""
    keys = {
        "expires": lambda i: (i.expires, i.name.casefold()),
        "name": lambda i: (i.name.casefold(), i.expires),
        "category": lambda i: (i.category.casefold(), i.expires),
        "quantity": lambda i: (-i.quantity, i.expires),
    }
    if by not in keys:
        raise LarderError(f"unknown sort {by!r}; choose from {', '.join(keys)}")
    return sorted(items, key=keys[by])
