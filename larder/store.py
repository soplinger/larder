"""JSON persistence and CSV export for the pantry.

The file format is ``{"version": 1, "items": [...]}``. Unknown keys are
rejected rather than ignored, so a typo like ``"qantity"`` fails loudly
instead of silently losing a value.
"""

from __future__ import annotations

import csv
import io
import json
import os
import tempfile

from .core import DEFAULT_CATEGORY, DEFAULT_UNIT, Item, LarderError, make_item

FORMAT_VERSION = 1
_REQUIRED = {"name", "quantity", "expires"}
_OPTIONAL = {"unit", "category", "min_quantity"}
CSV_COLUMNS = ["name", "quantity", "unit", "category", "expires", "min_quantity"]


def item_to_dict(item: Item) -> dict:
    return {
        "name": item.name,
        "quantity": item.quantity,
        "unit": item.unit,
        "category": item.category,
        "expires": item.expires.isoformat(),
        "min_quantity": item.min_quantity,
    }


def item_from_dict(data: object, where: str = "item") -> Item:
    if not isinstance(data, dict):
        raise LarderError(f"{where} must be an object")
    missing = _REQUIRED - set(data)
    if missing:
        raise LarderError(f"{where} is missing {', '.join(sorted(missing))}")
    unknown = set(data) - _REQUIRED - _OPTIONAL
    if unknown:
        raise LarderError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")
    try:
        return make_item(
            data["name"],
            data["quantity"],
            data["expires"],
            unit=data.get("unit", DEFAULT_UNIT),
            category=data.get("category", DEFAULT_CATEGORY),
            min_quantity=data.get("min_quantity", 0),
        )
    except LarderError as exc:
        raise LarderError(f"{where}: {exc}") from None


def load(path: str) -> list[Item]:
    """Read the pantry from ``path``. A missing file means an empty pantry."""
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            data = json.load(handle)
    except json.JSONDecodeError as exc:
        raise LarderError(f"{path} is not valid JSON ({exc.msg} at line {exc.lineno})") from None
    except UnicodeDecodeError:
        raise LarderError(f"{path} is not UTF-8 text") from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise LarderError(f"{path} must contain an object with an \"items\" list")
    if data.get("version", FORMAT_VERSION) != FORMAT_VERSION:
        raise LarderError(f"{path} has unsupported version {data.get('version')!r}")
    return [item_from_dict(entry, f"items[{i}]") for i, entry in enumerate(data["items"])]


def save(path: str, items: list[Item]) -> None:
    """Write the pantry atomically: a temp file in the same folder, then ``os.replace``.

    A crash mid-write leaves the previous file intact.
    """
    payload = {"version": FORMAT_VERSION, "items": [item_to_dict(i) for i in items]}
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".larder-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
        raise


def to_csv(items: list[Item]) -> str:
    """Render the pantry as CSV text with a header row."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for item in items:
        row = item_to_dict(item)
        writer.writerow([row[column] for column in CSV_COLUMNS])
    return buffer.getvalue()
