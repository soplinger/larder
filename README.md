# 🥫 Larder

**A pantry tracker that knows what's about to go off.**

Larder keeps a record of everything in your cupboard, fridge and freezer: how much you have, what unit it's in, and when it expires. It tells you what to use first, what has already gone bad, and what to buy to get back to the stock levels you want. It's a command-line tool built on the Python standard library only: no accounts, no servers, no network calls.

## ✨ Features

- **Add stock** with quantity, unit, expiry date, category and a minimum level to keep on hand
- **Merge automatically**: adding the same thing with the same expiry date adds to the existing line
- **First-expired, first-used**: `use` takes the soonest-expiring unexpired stock first, across as many lines as needed; expired stock is never used
- **Unit safety**: if the same name is stored in two units (say grams and bags), `use` refuses to guess and asks for `--unit`
- **Expiring soon**: lists what expires in the next *N* days (default 7)
- **Expired report**: lists what's already past its date
- **Low-stock report**: items below their minimum, with have/minimum counts
- **Shopping list**: how much to buy to reach each minimum, counting only unexpired stock
- **Sorted, filterable listing** by expiry, name, category or quantity, with a category filter
- **Category summary**: line counts and expired counts per category
- **Remove** all lines for an item, or just the one expiring on a specific date
- **CSV export** to stdout, ready for a spreadsheet
- **Safe storage**: validated JSON, unknown fields rejected, atomic saves that never leave a half-written file
- **Planning mode**: `--today` evaluates everything as of any date you choose
- **Clear errors**: bad dates, bad numbers and corrupt files produce a one-line message and exit code 1

## 🚀 Quick start

Requires Python 3.9 or newer. Run these from the project folder:

```bash
python3 -m larder add "Greek yogurt" 2 2026-10-22 --category Dairy --min 4
python3 -m larder add Eggs 6 2026-10-19 --category Dairy --min 6
python3 -m larder add Rice 2 2027-03-01 --unit kg --category Grains --min 5
python3 -m larder --today 2026-10-17 use Eggs 2
python3 -m larder --today 2026-10-17 list
python3 -m larder --today 2026-10-17 shopping
```

Expected output of the last two commands:

```text
NAME          QTY  UNIT  CATEGORY  EXPIRES     STATUS
------------  ---  ----  --------  ----------  -------
Eggs          4    pcs   Dairy     2026-10-19  in 2d
Greek yogurt  2    pcs   Dairy     2026-10-22  in 5d
Rice          2    kg    Grains    2027-03-01  in 135d

ITEM          AMOUNT  UNIT  NOTE
------------  ------  ----  -----------------
Eggs          2       pcs   have 4, minimum 6
Greek yogurt  2       pcs   have 2, minimum 4
Rice          3       kg    have 2, minimum 5
```

Larder saves its data to `larder.json` in the current folder. Use `--file` or the `LARDER_FILE` environment variable to choose another location.

## 🧭 Command reference

| Command | What it does |
| --- | --- |
| `add NAME QTY EXPIRES [--unit U] [--category C] [--min N]` | Add stock |
| `list [--sort KEY] [--category C]` | Show everything |
| `expiring [--days N]` | Show stock expiring within N days |
| `expired` | Show stock already past its date |
| `use NAME AMOUNT [--unit U]` | Use stock, soonest-expiring first |
| `remove NAME [--expires DATE]` | Throw stock away |
| `low` | Show items below their minimum |
| `shopping` | Show how much to buy |
| `stats` | Summarise by category |
| `export` | Print the pantry as CSV |

Global options go before the command: `--file PATH` and `--today YYYY-MM-DD`.

## 🛠 How to run

```bash
python3 -m larder --help
python3 -m larder --version
python3 -m larder --file kitchen.json add Milk 1 2026-10-30
python3 -m larder --file kitchen.json stats
```

Exit codes: `0` on success, `1` for a problem with your input or data file, `2` for a usage error such as an unknown command or sort key.

## ✅ How to test

The tests use only `unittest`, so they run without anything installed:

```bash
python3 -m unittest discover -s tests -t .
```

If you have pytest installed, it runs the same tests:

```bash
python3 -m pytest -q
```

The suite covers the core rules (FIFO usage, date boundaries, merging, shortfalls that ignore expired stock), the storage layer (round trips, rejected fields, corrupt files, CSV quoting) and the CLI end to end. Temporary files are created inside the project and removed afterwards.

## 📁 Project layout

```text
larder/
  core.py     pure rules: validation, expiry, FIFO usage, shortfalls
  store.py    JSON load/save (atomic) and CSV export
  cli.py      argparse commands that tie the two together
  __main__.py makes `python3 -m larder` work
tests/
  test_core.py, test_store.py, test_cli.py
```

## 📝 Data format

```json
{
  "version": 1,
  "items": [
    {"name": "Eggs", "quantity": 4, "unit": "pcs", "category": "Dairy",
     "expires": "2026-10-19", "min_quantity": 6}
  ]
}
```

`unit`, `category` and `min_quantity` are optional and take the defaults `pcs`, `Uncategorized` and `0`. Any other field is an error.
